export default function PinnacleLogo({ size = 32, className = '' }) {
  return (
    <span
      className={`relative inline-flex items-center justify-center rounded-xl bg-primary shrink-0 ${className}`}
      style={{ height: size, width: size }}
      data-testid="pinnacle-logo"
    >
      <svg viewBox="0 0 24 24" width={size * 0.6} height={size * 0.6} fill="none">
        <path
          d="M3.5 15.5c2.5-5.5 5.5-5.5 7.5-1.5s4.5 3.5 7-1.5"
          stroke="white"
          strokeWidth={2.3}
          strokeLinecap="round"
          fill="none"
        />
        <circle cx="18.5" cy="7.2" r="1.8" fill="white" />
      </svg>
    </span>
  );
}
