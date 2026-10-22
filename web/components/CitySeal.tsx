/**
 * A seal-like city mark drawn with CSS only — a navy disc, a thin amber ring
 * and a star. Used as the assistant avatar and the nav mark, so the demo needs
 * no image asset. Depends on nothing.
 */

export default function CitySeal({
  size = 28,
  onDark = false,
}: {
  size?: number;
  onDark?: boolean;
}) {
  return (
    <span
      aria-hidden="true"
      style={{ width: size, height: size }}
      className={`inline-flex shrink-0 items-center justify-center rounded-full ring-1 ${
        onDark ? "bg-white/10 ring-white/40" : "bg-primary ring-accent"
      }`}
    >
      <span
        style={{ width: size * 0.62, height: size * 0.62, fontSize: size * 0.42 }}
        className="flex items-center justify-center rounded-full border border-accent/70 leading-none text-accent"
      >
        ★
      </span>
    </span>
  );
}
