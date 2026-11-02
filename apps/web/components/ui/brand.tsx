import Image from "next/image";
import Link from "next/link";

export function Brand() {
  return <Link href="/projects" className="flex shrink-0 items-center gap-3" aria-label="Plant Memory projects">
    <div className="relative h-12 w-32 overflow-hidden rounded bg-white">
      <Image src="/brand/spartan-controls.webp" alt="Spartan Controls" fill sizes="128px" className="object-cover scale-[1.55]" priority />
    </div>
    <span className="hidden border-l border-hairline pl-3 sm:block"><span className="block text-title font-bold text-ink">Plant Memory</span><span className="block text-[10px] uppercase tracking-[0.16em] text-muted">Engineering workspace · Demo</span></span>
  </Link>;
}
