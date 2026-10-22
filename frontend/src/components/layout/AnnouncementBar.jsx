import { useState } from "react";
import { Link } from "react-router-dom";
import { X } from "lucide-react";
import { SHELL } from "@/constants/testIds";
import { isDevData } from "@/lib/catalog";

const KEY = "av_announcement_dismissed_v1";

export const AnnouncementBar = () => {
  const [hidden, setHidden] = useState(() => localStorage.getItem(KEY) === "1");
  if (hidden) return null;
  const dismiss = () => {
    localStorage.setItem(KEY, "1");
    setHidden(true);
  };
  return (
    <div data-testid={SHELL.announcementBar} role="region" aria-label="Announcement" className="bg-av-indigo text-av-linen">
      <div className="av-container flex items-center justify-center gap-3 py-2 text-xs sm:text-sm">
        <p className="text-center">
          <span className="font-semibold text-av-gold">Preview</span> — AfroVending is in development.{isDevData() ? " Products and vendors shown are sample data." : " Payment opens in a later phase."}{" "}
          <Link to="/about" data-testid="announcement-learn-more-link" className="underline underline-offset-4 hover:text-av-gold">Learn more</Link>
        </p>
        <button type="button" onClick={dismiss} aria-label="Dismiss announcement" data-testid={SHELL.announcementDismiss}
          className="shrink-0 rounded-full p-1 hover:bg-white/10 transition-colors">
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};
