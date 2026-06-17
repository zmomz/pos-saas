import userEvent from '@testing-library/user-event';
import { screen } from '@testing-library/react';

/**
 * Drive a shadcn/Radix `<Select>` in component tests.
 *
 * A Radix Select is a `<button>` trigger plus a portalled listbox — it is NOT a
 * native `<select>`, so testing-library's `userEvent.selectOptions()` (a
 * native-element API) throws on it. This helper opens the trigger and clicks the
 * option by its VISIBLE TEXT (Radix options expose their label, not their
 * `value`), which is the supported way to operate the control.
 *
 * `pointerEventsCheck` is disabled because Radix sets `pointer-events: none` on
 * closed/animating layers; the default user-event guard would otherwise reject
 * the click in jsdom. The Pointer Capture / scrollIntoView stubs that Radix also
 * needs live in `src/test/setup.ts`.
 *
 * @param trigger  the SelectTrigger element (e.g. from `getByLabelText`)
 * @param optionName  the option's accessible name (visible text) to choose
 */
export async function selectOption(
  trigger: HTMLElement,
  optionName: RegExp | string
): Promise<void> {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  await user.click(trigger);
  const option = await screen.findByRole('option', { name: optionName });
  await user.click(option);
}
