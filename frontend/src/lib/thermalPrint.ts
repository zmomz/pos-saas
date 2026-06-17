/**
 * WebUSB thermal-printer helper (Phase E).
 *
 * Takes the base64 ESC/POS byte stream produced by
 * `GET /api/v1/pos/transactions/{id}/escpos` and streams it to a USB thermal
 * printer via the WebUSB API. WebUSB is Chromium-only and requires a secure
 * context (https or localhost); `isThermalPrintSupported()` lets callers
 * feature-gate the button.
 */

// Minimal WebUSB typings (the DOM lib doesn't always include them).
interface USBLike {
  requestDevice(opts: { filters: unknown[] }): Promise<USBDeviceLike>;
}
interface USBDeviceLike {
  open(): Promise<void>;
  selectConfiguration(n: number): Promise<void>;
  claimInterface(n: number): Promise<void>;
  configuration?: { interfaces: Array<{ interfaceNumber: number; alternate: { endpoints: Array<{ direction: string; endpointNumber: number }> } }> };
  transferOut(endpoint: number, data: BufferSource | Uint8Array): Promise<unknown>;
  close(): Promise<void>;
}

export function isThermalPrintSupported(): boolean {
  return typeof navigator !== 'undefined' && 'usb' in navigator;
}

function base64ToBytes(b64: string): Uint8Array {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/**
 * Prompt the user to pick a USB printer and send the ESC/POS payload.
 * Throws on cancellation or transfer failure so callers can surface a toast.
 */
export async function printEscPos(base64Payload: string): Promise<void> {
  if (!isThermalPrintSupported()) {
    throw new Error('WebUSB is not supported in this browser.');
  }
  const usb = (navigator as unknown as { usb: USBLike }).usb;

  // No vendor filter — let the user choose any connected printer.
  const device = await usb.requestDevice({ filters: [] });
  await device.open();
  if (!device.configuration) await device.selectConfiguration(1);

  // Find the first interface with a bulk OUT endpoint.
  const iface = device.configuration?.interfaces?.[0];
  const interfaceNumber = iface?.interfaceNumber ?? 0;
  await device.claimInterface(interfaceNumber);

  const outEndpoint =
    iface?.alternate?.endpoints?.find((e) => e.direction === 'out')
      ?.endpointNumber ?? 1;

  try {
    await device.transferOut(outEndpoint, base64ToBytes(base64Payload));
  } finally {
    await device.close();
  }
}
