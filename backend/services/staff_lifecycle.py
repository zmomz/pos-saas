"""Staff lifecycle service (#216).

Real workforce management on top of the staff directory:

* **Lifecycle** — suspend / terminate / reactivate a staff member. Suspending or
  terminating revokes the member's *own* login access immediately: their bound
  ``login_user_id`` security stamp (``token_version``) is bumped so every live
  token dies, and the auth layer additionally blocks any staff whose status is
  not ``active`` (defence in depth — see ``dependencies.auth``).
* **PIN login** — set/clear a numeric PIN (bcrypt-hashed) and authenticate a
  staff member by ``(merchant, pin)`` from a shared terminal.
* **Attendance** — clock in / clock out, with worked-hours derived at read time.
* **Shift assignment** — roster a staff member to a planned shift window.
* **Export** — attendance/hours as CSV for downstream payroll (export only).

Every operation is scoped to the owning merchant (``owner_user_id``) so one
merchant can never touch another's workforce.
"""
import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import hash_password, verify_password
from models.auth import User
from models.staff_attendance import Staff_attendance
from models.staff_members import Staff_members
from models.staff_shift_assignments import Staff_shift_assignments

logger = logging.getLogger(__name__)

# The lifecycle states a staff member can hold. ``active`` is the only one that
# permits login; the other two revoke access (suspended is reversible).
STAFF_STATUSES = frozenset({"active", "suspended", "terminated"})
ACCESS_REVOKED_STATUSES = frozenset({"suspended", "terminated"})

# A PIN must be 4–8 digits — long enough to resist a casual shoulder-surf guess,
# short enough for a cashier to key quickly. Brute force is additionally throttled
# at the login endpoint and scoped to a single merchant.
PIN_MIN_LEN = 4
PIN_MAX_LEN = 8


def validate_pin(pin: str) -> str:
    """Return the PIN if it is 4–8 digits, else raise ``ValueError``."""
    if not isinstance(pin, str) or not pin.isdigit():
        raise ValueError("PIN must be numeric")
    if not (PIN_MIN_LEN <= len(pin) <= PIN_MAX_LEN):
        raise ValueError(f"PIN must be {PIN_MIN_LEN}-{PIN_MAX_LEN} digits")
    return pin


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def worked_hours(clock_in: Optional[datetime], clock_out: Optional[datetime]) -> Optional[float]:
    """Hours between clock-in and clock-out, rounded to 2dp; ``None`` if still open."""
    ci, co = _as_utc(clock_in), _as_utc(clock_out)
    if ci is None or co is None:
        return None
    return round(max(0.0, (co - ci).total_seconds() / 3600.0), 2)


class StaffLifecycleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_staff(self, staff_id: int, owner_user_id: str) -> Optional[Staff_members]:
        """Owner-scoped staff fetch — never crosses the tenancy boundary."""
        result = await self.db.execute(
            select(Staff_members).where(
                Staff_members.id == staff_id,
                Staff_members.user_id == str(owner_user_id),
            )
        )
        return result.scalar_one_or_none()

    # ----------------------------- lifecycle -----------------------------
    async def set_status(
        self, staff_id: int, owner_user_id: str, status: str
    ) -> Optional[Staff_members]:
        """Move a staff member to ``status`` and revoke their login if access is cut.

        Returns the updated row, or ``None`` if no such staff under this owner.
        """
        if status not in STAFF_STATUSES:
            raise ValueError(f"Invalid status: {status}")

        staff = await self._get_staff(staff_id, owner_user_id)
        if not staff:
            return None

        staff.status = status
        # Keep the legacy ``is_active`` toggle in lockstep so existing list filters
        # and the SEC-06 cascade tests stay coherent.
        staff.is_active = status == "active"

        if status in ACCESS_REVOKED_STATUSES and staff.login_user_id:
            # Drop every live session for the staff member's own login by bumping
            # its security stamp — mirrors the password-reset revocation path.
            login = (
                await self.db.execute(select(User).where(User.id == staff.login_user_id))
            ).scalar_one_or_none()
            if login is not None:
                login.token_version = int(getattr(login, "token_version", 0) or 0) + 1

        await self.db.commit()
        await self.db.refresh(staff)
        logger.info("Staff %s status -> %s (owner %s)", staff_id, status, owner_user_id)
        return staff

    # -------------------------------- PIN --------------------------------
    async def set_pin(
        self, staff_id: int, owner_user_id: str, pin: Optional[str]
    ) -> Optional[Staff_members]:
        """Set (or clear, when ``pin`` is ``None``) a staff member's login PIN."""
        staff = await self._get_staff(staff_id, owner_user_id)
        if not staff:
            return None
        if pin is None:
            staff.pin_hash = None
        else:
            staff.pin_hash = hash_password(validate_pin(pin))
        await self.db.commit()
        await self.db.refresh(staff)
        return staff

    async def authenticate_pin(self, owner_user_id: str, pin: str) -> Optional[Staff_members]:
        """Return the active, login-bound staff member under ``owner_user_id`` whose
        PIN matches, else ``None``.

        Candidates are scanned and bcrypt-verified one by one because a salted hash
        can't be queried directly; the set is one merchant's staff, so it is small.
        Only ``active`` members with a bound login can authenticate.
        """
        if not pin or not pin.isdigit():
            return None
        rows = (
            await self.db.execute(
                select(Staff_members).where(
                    Staff_members.user_id == str(owner_user_id),
                    Staff_members.pin_hash.isnot(None),
                )
            )
        ).scalars().all()
        for staff in rows:
            if staff.status in ACCESS_REVOKED_STATUSES or not staff.login_user_id:
                continue
            if verify_password(pin, staff.pin_hash):
                return staff
        return None

    # ----------------------------- attendance -----------------------------
    async def open_attendance(self, staff_id: int, owner_user_id: str) -> Optional[Staff_attendance]:
        """Return the staff member's currently-open (un-clocked-out) record, if any."""
        result = await self.db.execute(
            select(Staff_attendance).where(
                Staff_attendance.user_id == str(owner_user_id),
                Staff_attendance.staff_id == staff_id,
                Staff_attendance.clock_out.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def clock_in(
        self,
        staff_id: int,
        owner_user_id: str,
        branch_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> Staff_attendance:
        """Open a new attendance record. Raises ``ValueError`` if one is already open."""
        staff = await self._get_staff(staff_id, owner_user_id)
        if not staff:
            raise ValueError("Staff member not found")
        if staff.status in ACCESS_REVOKED_STATUSES:
            raise ValueError("Cannot clock in a suspended or terminated staff member")
        if await self.open_attendance(staff_id, owner_user_id):
            raise ValueError("Staff member is already clocked in")
        rec = Staff_attendance(
            user_id=str(owner_user_id),
            staff_id=staff_id,
            branch_id=branch_id,
            clock_in=datetime.now(timezone.utc),
            notes=notes,
        )
        self.db.add(rec)
        await self.db.commit()
        await self.db.refresh(rec)
        return rec

    async def clock_out(self, staff_id: int, owner_user_id: str) -> Staff_attendance:
        """Close the open attendance record. Raises ``ValueError`` if none is open."""
        rec = await self.open_attendance(staff_id, owner_user_id)
        if not rec:
            raise ValueError("Staff member is not clocked in")
        rec.clock_out = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(rec)
        return rec

    async def list_attendance(
        self,
        owner_user_id: str,
        staff_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 200,
    ) -> List[Staff_attendance]:
        query = select(Staff_attendance).where(Staff_attendance.user_id == str(owner_user_id))
        if staff_id is not None:
            query = query.where(Staff_attendance.staff_id == staff_id)
        query = query.order_by(Staff_attendance.clock_in.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # --------------------------- shift assignment ---------------------------
    async def assign_shift(
        self,
        staff_id: int,
        owner_user_id: str,
        starts_at: datetime,
        ends_at: datetime,
        branch_id: Optional[int] = None,
        role: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Staff_shift_assignments:
        staff = await self._get_staff(staff_id, owner_user_id)
        if not staff:
            raise ValueError("Staff member not found")
        if _as_utc(ends_at) <= _as_utc(starts_at):
            raise ValueError("Shift end must be after its start")
        shift = Staff_shift_assignments(
            user_id=str(owner_user_id),
            staff_id=staff_id,
            branch_id=branch_id,
            starts_at=starts_at,
            ends_at=ends_at,
            role=role,
            notes=notes,
            status="scheduled",
        )
        self.db.add(shift)
        await self.db.commit()
        await self.db.refresh(shift)
        return shift

    async def list_shifts(
        self,
        owner_user_id: str,
        staff_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 200,
    ) -> List[Staff_shift_assignments]:
        query = select(Staff_shift_assignments).where(
            Staff_shift_assignments.user_id == str(owner_user_id)
        )
        if staff_id is not None:
            query = query.where(Staff_shift_assignments.staff_id == staff_id)
        query = query.order_by(Staff_shift_assignments.starts_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def cancel_shift(self, shift_id: int, owner_user_id: str) -> Optional[Staff_shift_assignments]:
        result = await self.db.execute(
            select(Staff_shift_assignments).where(
                Staff_shift_assignments.id == shift_id,
                Staff_shift_assignments.user_id == str(owner_user_id),
            )
        )
        shift = result.scalar_one_or_none()
        if not shift:
            return None
        shift.status = "cancelled"
        await self.db.commit()
        await self.db.refresh(shift)
        return shift

    # ------------------------------- export -------------------------------
    async def attendance_csv(self, owner_user_id: str) -> str:
        """Owner-scoped attendance export for payroll (rows + derived hours)."""
        records = await self.list_attendance(owner_user_id, limit=2000)
        # Resolve staff names once so the export is human-readable.
        names: Dict[int, str] = {}
        staff_rows = (
            await self.db.execute(
                select(Staff_members).where(Staff_members.user_id == str(owner_user_id))
            )
        ).scalars().all()
        for s in staff_rows:
            names[s.id] = s.name

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["staff_id", "staff_name", "branch_id", "clock_in", "clock_out", "hours"]
        )
        for r in records:
            ci = _as_utc(r.clock_in)
            co = _as_utc(r.clock_out)
            hrs = worked_hours(r.clock_in, r.clock_out)
            writer.writerow(
                [
                    r.staff_id,
                    names.get(r.staff_id, ""),
                    r.branch_id if r.branch_id is not None else "",
                    ci.isoformat() if ci else "",
                    co.isoformat() if co else "",
                    "" if hrs is None else f"{hrs:.2f}",
                ]
            )
        return buf.getvalue()


def attendance_to_dict(rec: Staff_attendance) -> Dict[str, Any]:
    """Serialise an attendance row + derived hours for the API."""
    return {
        "id": rec.id,
        "staff_id": rec.staff_id,
        "branch_id": rec.branch_id,
        "clock_in": rec.clock_in,
        "clock_out": rec.clock_out,
        "hours": worked_hours(rec.clock_in, rec.clock_out),
        "notes": rec.notes,
    }


def shift_to_dict(shift: Staff_shift_assignments) -> Dict[str, Any]:
    return {
        "id": shift.id,
        "staff_id": shift.staff_id,
        "branch_id": shift.branch_id,
        "starts_at": shift.starts_at,
        "ends_at": shift.ends_at,
        "role": shift.role,
        "notes": shift.notes,
        "status": shift.status,
    }
