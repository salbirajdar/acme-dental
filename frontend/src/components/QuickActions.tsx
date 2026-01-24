import './QuickActions.css';

interface QuickActionsProps {
  onAction: (action: string) => void;
  disabled: boolean;
}

const QUICK_ACTIONS = [
  { label: 'Book Appointment', message: 'I would like to book an appointment' },
  { label: 'Check My Booking', message: 'Can you check my existing booking?' },
  { label: 'View Prices', message: 'What are your prices?' },
  { label: 'Office Hours', message: 'What are your office hours?' },
];

export function QuickActions({ onAction, disabled }: QuickActionsProps) {
  return (
    <div className="quick-actions">
      {QUICK_ACTIONS.map((action) => (
        <button
          key={action.label}
          className="quick-action-btn"
          onClick={() => onAction(action.message)}
          disabled={disabled}
        >
          {action.label}
        </button>
      ))}
    </div>
  );
}
