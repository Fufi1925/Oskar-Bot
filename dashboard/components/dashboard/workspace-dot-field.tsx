"use client";

import { useEffect, useRef } from "react";

/** A visual backdrop that leaves links and editors available to the pointer. */
export function WorkspaceDotField() {
  const dots = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let frame = 0;
    const move = (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        dots.current?.style.setProperty("--workspace-pointer-x", `${event.clientX}px`);
        dots.current?.style.setProperty("--workspace-pointer-y", `${event.clientY}px`);
        dots.current?.style.setProperty("--workspace-pointer-visible", "1");
      });
    };
    const leave = () => { cancelAnimationFrame(frame); dots.current?.style.setProperty("--workspace-pointer-visible", "0"); };
    window.addEventListener("pointermove", move);
    document.documentElement.addEventListener("pointerleave", leave);
    window.addEventListener("blur", leave);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("pointermove", move); document.documentElement.removeEventListener("pointerleave", leave); window.removeEventListener("blur", leave); };
  }, []);
  return <div ref={dots} className="cloudtix-workspace-dots" aria-hidden="true" />;
}
