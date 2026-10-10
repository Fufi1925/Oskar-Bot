"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import "./public-website-surface.css";

/** One public backdrop. Dashboard routes keep their existing layout and palette. */
export function PublicWebsiteSurface({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const publicPage = pathname !== "/dashboard" && !pathname.startsWith("/dashboard/") && !pathname.startsWith("/api/");
  const highlight = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!publicPage) return;
    const layer = highlight.current;
    if (!layer) return;
    const mouse = window.matchMedia("(hover: hover) and (pointer: fine)");
    let frame = 0;
    let x = 0;
    let y = 0;

    const clear = () => {
      window.cancelAnimationFrame(frame);
      frame = 0;
      layer.style.opacity = "0";
    };
    const move = (event: PointerEvent) => {
      if (!mouse.matches || event.pointerType === "touch") return;
      x = event.clientX;
      y = event.clientY;
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        layer.style.setProperty("--dot-pointer-x", `${x}px`);
        layer.style.setProperty("--dot-pointer-y", `${y}px`);
        layer.style.opacity = "1";
        frame = 0;
      });
    };
    const visibility = () => { if (document.hidden) clear(); };
    window.addEventListener("pointermove", move, { passive: true });
    window.addEventListener("blur", clear);
    document.documentElement.addEventListener("pointerleave", clear);
    document.addEventListener("visibilitychange", visibility);
    mouse.addEventListener("change", clear);
    return () => {
      clear();
      window.removeEventListener("pointermove", move);
      window.removeEventListener("blur", clear);
      document.documentElement.removeEventListener("pointerleave", clear);
      document.removeEventListener("visibilitychange", visibility);
      mouse.removeEventListener("change", clear);
    };
  }, [publicPage, pathname]);

  if (!publicPage) return <>{children}</>;

  return (
    <div className="cloudtix-public-site">
      <div className="cloudtix-dot-backdrop" aria-hidden="true">
        <div className="cloudtix-dot-grid" />
        <div ref={highlight} className="cloudtix-dot-grid cloudtix-dot-highlight" />
      </div>
      {children}
    </div>
  );
}
