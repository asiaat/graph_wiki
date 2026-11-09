import React, { useEffect, useRef, useState } from "react";
import { Maximize2, Minimize2 } from "lucide-react";

interface FullscreenFrameProps {
  title: string;
  children: React.ReactNode | ((isFullscreen: boolean) => React.ReactNode);
  className?: string;
  fullscreenClassName?: string;
}

export default function FullscreenFrame({
  title,
  children,
  className,
  fullscreenClassName,
}: FullscreenFrameProps) {
  const frameRef = useRef<HTMLElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const syncFullscreen = () => {
      setIsFullscreen(document.fullscreenElement === frameRef.current);
    };
    const exitOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && document.fullscreenElement === frameRef.current) {
        void document.exitFullscreen();
      }
    };
    document.addEventListener("fullscreenchange", syncFullscreen);
    document.addEventListener("keydown", exitOnEscape);
    return () => {
      document.removeEventListener("fullscreenchange", syncFullscreen);
      document.removeEventListener("keydown", exitOnEscape);
    };
  }, []);

  async function toggleFullscreen() {
    if (document.fullscreenElement === frameRef.current) {
      await document.exitFullscreen();
    } else {
      await frameRef.current?.requestFullscreen();
    }
  }

  const content = typeof children === "function" ? children(isFullscreen) : children;

  return (
    <section
      ref={frameRef}
      className={`relative min-w-0 ${className ?? "rounded-lg border border-slate-200 bg-white"} ${isFullscreen ? (fullscreenClassName ?? "overflow-auto p-4") : "overflow-hidden"}`}
    >
      <button
        type="button"
        className="absolute right-2 top-2 z-10 rounded-md border border-slate-200 bg-white/95 p-2 text-slate-600 shadow-sm hover:bg-slate-50 hover:text-slate-900"
        onClick={() => void toggleFullscreen()}
        aria-label={isFullscreen ? `Exit ${title} full screen` : `Open ${title} full screen`}
        title={isFullscreen ? "Exit full screen (Esc)" : "Open this frame full screen"}
      >
        {isFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
      </button>
      {content}
    </section>
  );
}
