export default function PinnacleLogo({ size = 32, className = '' }) {
  return (
    <span
      className={`relative inline-flex items-center justify-center rounded-xl bg-primary shrink-0 ${className}`}
      style={{ height: size, width: size }}
      data-testid="pinnacle-logo"
    >
      <span className="font-display font-extrabold text-primary-foreground" style={{ fontSize: size * 0.56, lineHeight: 1 }}>
        P
      </span>
      <span
        className="absolute rounded-full bg-[#f97316]"
        style={{ width: size * 0.16, height: size * 0.16, right: size * 0.15, bottom: size * 0.17 }}
      />
    </span>
  );
}
