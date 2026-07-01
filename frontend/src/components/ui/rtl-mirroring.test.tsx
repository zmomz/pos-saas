import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbSeparator,
} from './breadcrumb';
import { Calendar } from './calendar';

// ISSUE-226 (a11y) — RTL layout: directional chevrons/arrows must mirror in
// right-to-left languages (Arabic/Urdu). A breadcrumb separator and calendar
// month-nav arrows point in a reading direction; unmirrored they point the
// wrong way in RTL. Tailwind's `rtl:rotate-180` variant flips them under a
// `[dir="rtl"]` ancestor. These primitives are shared across the whole app, so
// asserting the class here covers every consumer.

function classesOf(el: Element | null): string {
  return el?.getAttribute('class') ?? '';
}

describe('RTL directional-icon mirroring (ISSUE-226)', () => {
  it('mirrors the breadcrumb separator chevron', () => {
    const { container } = render(
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink href="/">Home</BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
        </BreadcrumbList>
      </Breadcrumb>
    );

    const separator = container.querySelector('[role="presentation"] svg');
    expect(separator).not.toBeNull();
    expect(classesOf(separator)).toContain('rtl:rotate-180');
  });

  it('mirrors the calendar month-navigation arrows', () => {
    const { container } = render(<Calendar />);

    const navIcons = Array.from(container.querySelectorAll('svg')).filter((svg) =>
      classesOf(svg).includes('rtl:rotate-180')
    );
    // Both the previous and next month arrows must be mirrored.
    expect(navIcons.length).toBeGreaterThanOrEqual(2);
  });
});
