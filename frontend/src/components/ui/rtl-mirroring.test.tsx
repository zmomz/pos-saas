import { describe, it, expect } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbSeparator,
} from './breadcrumb';
import { Calendar } from './calendar';
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselPrevious,
  CarouselNext,
} from './carousel';
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationPrevious,
  PaginationNext,
} from './pagination';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
} from './dropdown-menu';
import {
  ContextMenu,
  ContextMenuTrigger,
  ContextMenuContent,
  ContextMenuSub,
  ContextMenuSubTrigger,
} from './context-menu';
import {
  Menubar,
  MenubarMenu,
  MenubarTrigger,
  MenubarContent,
  MenubarSub,
  MenubarSubTrigger,
} from './menubar';

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

  it('mirrors the carousel previous/next arrows', () => {
    const { container } = render(
      <Carousel>
        <CarouselContent>
          <CarouselItem>Slide</CarouselItem>
        </CarouselContent>
        <CarouselPrevious />
        <CarouselNext />
      </Carousel>
    );

    const navIcons = Array.from(container.querySelectorAll('svg')).filter((svg) =>
      classesOf(svg).includes('rtl:rotate-180')
    );
    // Both the previous and next slide arrows must be mirrored.
    expect(navIcons.length).toBeGreaterThanOrEqual(2);
  });

  it('mirrors the pagination previous/next chevrons', () => {
    const { container } = render(
      <Pagination>
        <PaginationContent>
          <PaginationItem>
            <PaginationPrevious href="#" />
          </PaginationItem>
          <PaginationItem>
            <PaginationNext href="#" />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    );

    const navIcons = Array.from(container.querySelectorAll('svg')).filter((svg) =>
      classesOf(svg).includes('rtl:rotate-180')
    );
    // Both the previous and next page chevrons must be mirrored.
    expect(navIcons.length).toBeGreaterThanOrEqual(2);
  });

  // Submenu triggers render a trailing ChevronRight that points INTO the flyout;
  // it must flip in RTL so it still points toward where the submenu opens. Radix
  // menus portal their content, so open the whole chain (menu + sub) to mount it.
  it('mirrors the dropdown-menu submenu chevron', () => {
    render(
      <DropdownMenu defaultOpen>
        <DropdownMenuTrigger>Menu</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuSub open>
            <DropdownMenuSubTrigger>More</DropdownMenuSubTrigger>
          </DropdownMenuSub>
        </DropdownMenuContent>
      </DropdownMenu>
    );

    const chevron = document.querySelector('svg.rtl\\:rotate-180');
    expect(chevron).not.toBeNull();
  });

  it('mirrors the context-menu submenu chevron', () => {
    const { getByText } = render(
      <ContextMenu>
        <ContextMenuTrigger>Target</ContextMenuTrigger>
        <ContextMenuContent>
          <ContextMenuSub open>
            <ContextMenuSubTrigger>More</ContextMenuSubTrigger>
          </ContextMenuSub>
        </ContextMenuContent>
      </ContextMenu>
    );
    // Context menus open on right-click; nothing mounts until then.
    fireEvent.contextMenu(getByText('Target'));

    const chevron = document.querySelector('svg.rtl\\:rotate-180');
    expect(chevron).not.toBeNull();
  });

  it('mirrors the menubar submenu chevron', () => {
    render(
      <Menubar defaultValue="file">
        <MenubarMenu value="file">
          <MenubarTrigger>File</MenubarTrigger>
          <MenubarContent>
            <MenubarSub open>
              <MenubarSubTrigger>More</MenubarSubTrigger>
            </MenubarSub>
          </MenubarContent>
        </MenubarMenu>
      </Menubar>
    );

    const chevron = document.querySelector('svg.rtl\\:rotate-180');
    expect(chevron).not.toBeNull();
  });
});
