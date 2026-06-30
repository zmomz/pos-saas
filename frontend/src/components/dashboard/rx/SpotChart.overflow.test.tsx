import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import SpotChart from './SpotChart';

// ISSUE-244 — the absolutely-positioned hover tooltip is translated -50% on x, so
// at the chart edges it can overflow its container and trigger a phantom
// horizontal scrollbar. The plot wrapper must clip horizontal overflow so the
// tooltip can never misrender, even once the hover path is wired.

describe('SpotChart overflow guard (ISSUE-244)', () => {
  it('clips horizontal overflow on the plot wrapper', () => {
    const { container } = render(
      <SpotChart
        series={{ '12M': [1, 2, 3, 4, 5] }}
        labels={{ '12M': ['a', 'b', 'c', 'd', 'e'] }}
        ranges={['12M']}
        format={(n) => String(n)}
      />
    );
    // The wrapper holding the <svg> + absolute tooltip must guard overflow-x.
    expect(container.querySelector('.overflow-x-clip')).not.toBeNull();
  });
});
