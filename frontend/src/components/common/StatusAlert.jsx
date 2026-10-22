import { Info, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

const TONES = {
  info: { icon: Info, cls: "border-av-indigo/20 bg-av-indigo-light text-av-indigo [&>svg]:text-av-indigo" },
  success: { icon: CheckCircle2, cls: "border-av-emerald/25 bg-av-emerald-light text-av-emerald [&>svg]:text-av-emerald" },
  warning: { icon: AlertTriangle, cls: "border-av-gold/30 bg-av-gold-light text-av-gold-deep [&>svg]:text-av-gold-deep" },
  error: { icon: XCircle, cls: "border-red-300 bg-red-50 text-red-800 [&>svg]:text-red-700" },
};

export const StatusAlert = ({ tone = "info", title, children, testId, className }) => {
  const { icon: Icon, cls } = TONES[tone];
  return (
    <Alert data-testid={testId} role={tone === "error" ? "alert" : "status"} className={cn("rounded-xl", cls, className)}>
      <Icon className="h-4 w-4" />
      <AlertTitle className="font-semibold">{title}</AlertTitle>
      {children && <AlertDescription>{children}</AlertDescription>}
    </Alert>
  );
};
