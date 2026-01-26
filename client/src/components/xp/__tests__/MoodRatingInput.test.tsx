import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '../../../test/utils';
import { MoodRatingInput } from '../MoodRatingInput';

describe('MoodRatingInput', () => {
  const moods = [
    { value: 1, emoji: '😞', label: 'Very Bad' },
    { value: 2, emoji: '😕', label: 'Bad' },
    { value: 3, emoji: '😐', label: 'Okay' },
    { value: 4, emoji: '🙂', label: 'Good' },
    { value: 5, emoji: '😄', label: 'Great' },
  ];

  describe('rendering', () => {
    it('renders all 5 mood options as buttons', () => {
      const onChange = vi.fn();
      render(<MoodRatingInput value={3} onChange={onChange} />);

      const buttons = screen.getAllByRole('button');
      expect(buttons).toHaveLength(5);
    });

    it('displays all mood emojis', () => {
      const onChange = vi.fn();
      render(<MoodRatingInput value={3} onChange={onChange} />);

      moods.forEach(({ emoji }) => {
        expect(screen.getByText(emoji)).toBeInTheDocument();
      });
    });

    it('displays label for selected mood', () => {
      const onChange = vi.fn();

      moods.forEach(({ value, label }) => {
        const { unmount } = render(<MoodRatingInput value={value} onChange={onChange} />);
        expect(screen.getByText(label)).toBeInTheDocument();
        unmount();
      });
    });
  });

  describe('selection', () => {
    it('calls onChange with mood value when clicked', async () => {
      const onChange = vi.fn();
      const { user } = render(<MoodRatingInput value={3} onChange={onChange} />);

      await user.click(screen.getByText('😄'));

      expect(onChange).toHaveBeenCalledWith(5);
      expect(onChange).toHaveBeenCalledTimes(1);
    });

    it('calls onChange for each mood value', async () => {
      const onChange = vi.fn();
      const { user } = render(<MoodRatingInput value={3} onChange={onChange} />);

      for (const { emoji, value } of moods) {
        await user.click(screen.getByText(emoji));
        expect(onChange).toHaveBeenLastCalledWith(value);
      }

      expect(onChange).toHaveBeenCalledTimes(5);
    });
  });

  describe('hover behavior', () => {
    it('updates label on hover', async () => {
      const onChange = vi.fn();
      const { user } = render(<MoodRatingInput value={1} onChange={onChange} />);

      expect(screen.getByText('Very Bad')).toBeInTheDocument();

      await user.hover(screen.getByText('😄'));

      expect(screen.getByText('Great')).toBeInTheDocument();
      expect(screen.queryByText('Very Bad')).not.toBeInTheDocument();
    });

    it('restores original label on unhover', async () => {
      const onChange = vi.fn();
      const { user } = render(<MoodRatingInput value={2} onChange={onChange} />);

      await user.hover(screen.getByText('😄'));
      expect(screen.getByText('Great')).toBeInTheDocument();

      await user.unhover(screen.getByText('😄'));
      expect(screen.getByText('Bad')).toBeInTheDocument();
    });
  });

  describe('disabled state', () => {
    it('does not call onChange when disabled', async () => {
      const onChange = vi.fn();
      const { user } = render(<MoodRatingInput value={3} onChange={onChange} disabled />);

      await user.click(screen.getByText('😄'));

      expect(onChange).not.toHaveBeenCalled();
    });

    it('marks all buttons as disabled', () => {
      const onChange = vi.fn();
      render(<MoodRatingInput value={3} onChange={onChange} disabled />);

      const buttons = screen.getAllByRole('button');
      buttons.forEach((button) => {
        expect(button).toBeDisabled();
      });
    });

    it('does not update label on hover when disabled', async () => {
      const onChange = vi.fn();
      const { user } = render(<MoodRatingInput value={1} onChange={onChange} disabled />);

      expect(screen.getByText('Very Bad')).toBeInTheDocument();

      await user.hover(screen.getByText('😄'));

      // Should still show original label
      expect(screen.getByText('Very Bad')).toBeInTheDocument();
    });
  });

  describe('edge cases', () => {
    it('handles value of 0 (no selection)', () => {
      const onChange = vi.fn();
      render(<MoodRatingInput value={0} onChange={onChange} />);

      // Should render without crashing
      const buttons = screen.getAllByRole('button');
      expect(buttons).toHaveLength(5);
    });

    it('handles undefined onChange gracefully', async () => {
      // @ts-expect-error Testing runtime behavior with missing prop
      render(<MoodRatingInput value={3} onChange={undefined} />);

      // Should render without crashing
      expect(screen.getAllByRole('button')).toHaveLength(5);
    });
  });

  describe('accessibility', () => {
    it('buttons are focusable', () => {
      const onChange = vi.fn();
      render(<MoodRatingInput value={3} onChange={onChange} />);

      const buttons = screen.getAllByRole('button');
      buttons.forEach((button) => {
        expect(button).not.toHaveAttribute('tabindex', '-1');
      });
    });

    it('buttons have type="button" to prevent form submission', () => {
      const onChange = vi.fn();
      render(<MoodRatingInput value={3} onChange={onChange} />);

      const buttons = screen.getAllByRole('button');
      buttons.forEach((button) => {
        expect(button).toHaveAttribute('type', 'button');
      });
    });
  });
});
