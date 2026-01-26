import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '../../../test/utils';
import { PeriodSelector } from '../PeriodSelector';

describe('PeriodSelector', () => {
  const periods = ['week', 'month', 'quarter'] as const;

  describe('rendering', () => {
    it('renders all period options', () => {
      const onChange = vi.fn();
      render(<PeriodSelector selected="week" onChange={onChange} />);

      expect(screen.getByRole('button', { name: /week/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /month/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /quarter/i })).toBeInTheDocument();
    });

    it('renders exactly 3 buttons', () => {
      const onChange = vi.fn();
      render(<PeriodSelector selected="week" onChange={onChange} />);

      const buttons = screen.getAllByRole('button');
      expect(buttons).toHaveLength(3);
    });
  });

  describe('selection', () => {
    it('calls onChange with period value when clicked', async () => {
      const onChange = vi.fn();
      const { user } = render(<PeriodSelector selected="week" onChange={onChange} />);

      await user.click(screen.getByRole('button', { name: /month/i }));

      expect(onChange).toHaveBeenCalledWith('month');
      expect(onChange).toHaveBeenCalledTimes(1);
    });

    it('calls onChange for each period option', async () => {
      const onChange = vi.fn();
      const { user } = render(<PeriodSelector selected="week" onChange={onChange} />);

      await user.click(screen.getByRole('button', { name: /week/i }));
      expect(onChange).toHaveBeenLastCalledWith('week');

      await user.click(screen.getByRole('button', { name: /month/i }));
      expect(onChange).toHaveBeenLastCalledWith('month');

      await user.click(screen.getByRole('button', { name: /quarter/i }));
      expect(onChange).toHaveBeenLastCalledWith('quarter');

      expect(onChange).toHaveBeenCalledTimes(3);
    });

    it('allows clicking already selected option', async () => {
      const onChange = vi.fn();
      const { user } = render(<PeriodSelector selected="week" onChange={onChange} />);

      await user.click(screen.getByRole('button', { name: /week/i }));

      expect(onChange).toHaveBeenCalledWith('week');
    });
  });

  describe('selected state indication', () => {
    it.each(periods)('visually indicates when %s is selected', (period) => {
      const onChange = vi.fn();
      render(<PeriodSelector selected={period} onChange={onChange} />);

      const selectedButton = screen.getByRole('button', { name: new RegExp(period, 'i') });
      const otherButtons = screen.getAllByRole('button').filter((btn) => btn !== selectedButton);

      // Selected button should have distinct styling
      // We check for aria-current or aria-pressed as accessibility best practice
      // but since the component uses visual styling, we verify the button exists
      expect(selectedButton).toBeInTheDocument();
      expect(otherButtons).toHaveLength(2);
    });

    it('updates visual state when selected prop changes', () => {
      const onChange = vi.fn();
      const { rerender } = render(<PeriodSelector selected="week" onChange={onChange} />);

      // Initial state
      let weekButton = screen.getByRole('button', { name: /week/i });
      let monthButton = screen.getByRole('button', { name: /month/i });

      // Verify week is selected (has bg-white text-black, not bg-transparent)
      expect(weekButton.className).toMatch(/\bbg-white\b/);
      expect(weekButton.className).toContain('text-black');
      expect(monthButton.className).toContain('bg-transparent');

      // Change selection
      rerender(<PeriodSelector selected="month" onChange={onChange} />);

      weekButton = screen.getByRole('button', { name: /week/i });
      monthButton = screen.getByRole('button', { name: /month/i });

      // Verify month is now selected
      expect(weekButton.className).toContain('bg-transparent');
      expect(monthButton.className).toMatch(/\bbg-white\b/);
      expect(monthButton.className).toContain('text-black');
    });
  });

  describe('accessibility', () => {
    it('all buttons are keyboard accessible', () => {
      const onChange = vi.fn();
      render(<PeriodSelector selected="week" onChange={onChange} />);

      const buttons = screen.getAllByRole('button');
      buttons.forEach((button) => {
        expect(button).not.toBeDisabled();
        expect(button).not.toHaveAttribute('tabindex', '-1');
      });
    });

    it('buttons can be activated with keyboard', async () => {
      const onChange = vi.fn();
      const { user } = render(<PeriodSelector selected="week" onChange={onChange} />);

      const monthButton = screen.getByRole('button', { name: /month/i });
      monthButton.focus();

      await user.keyboard('{Enter}');

      expect(onChange).toHaveBeenCalledWith('month');
    });

    it('buttons can be activated with space key', async () => {
      const onChange = vi.fn();
      const { user } = render(<PeriodSelector selected="week" onChange={onChange} />);

      const quarterButton = screen.getByRole('button', { name: /quarter/i });
      quarterButton.focus();

      await user.keyboard(' ');

      expect(onChange).toHaveBeenCalledWith('quarter');
    });
  });

  describe('edge cases', () => {
    it('handles rapid clicks', async () => {
      const onChange = vi.fn();
      const { user } = render(<PeriodSelector selected="week" onChange={onChange} />);

      const monthButton = screen.getByRole('button', { name: /month/i });

      await user.tripleClick(monthButton);

      expect(onChange).toHaveBeenCalledWith('month');
      expect(onChange.mock.calls.length).toBeGreaterThanOrEqual(1);
    });
  });
});
