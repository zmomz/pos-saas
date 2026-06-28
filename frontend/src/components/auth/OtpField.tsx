import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp';

interface OtpFieldProps {
  value: string;
  onChange: (value: string) => void;
  /** Fires once the 6th digit is entered — wire to auto-submit. */
  onComplete?: (value: string) => void;
  disabled?: boolean;
  autoFocus?: boolean;
  'aria-label'?: string;
}

/**
 * Six-digit authenticator code entry (ISSUE-202). Wraps the shared `input-otp`
 * primitive in the petrol-token slot styling and keeps the digits LTR even in an
 * RTL layout — a TOTP code reads left-to-right in every locale.
 */
export default function OtpField({
  value,
  onChange,
  onComplete,
  disabled,
  autoFocus,
  'aria-label': ariaLabel,
}: OtpFieldProps) {
  return (
    <InputOTP
      maxLength={6}
      value={value}
      onChange={onChange}
      onComplete={onComplete}
      disabled={disabled}
      autoFocus={autoFocus}
      containerClassName="justify-center"
      aria-label={ariaLabel}
      dir="ltr"
      inputMode="numeric"
      pattern="[0-9]*"
    >
      <InputOTPGroup className="gap-2">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <InputOTPSlot
            key={i}
            index={i}
            className="h-12 w-11 rounded-lg border border-input text-lg font-semibold first:rounded-lg last:rounded-lg"
          />
        ))}
      </InputOTPGroup>
    </InputOTP>
  );
}
