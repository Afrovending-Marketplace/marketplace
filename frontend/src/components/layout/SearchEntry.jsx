import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { SHELL } from "@/constants/testIds";
import { cn } from "@/lib/utils";

export const SearchEntry = ({ compact = false, className }) => {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  const submit = (e) => {
    e.preventDefault();
    setOpen(false);
    navigate(`/search?q=${encodeURIComponent(q.trim())}`);
  };
  return (
    <div className={cn(className)}>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          {compact ? (
            <Button variant="ghost" size="icon" aria-label="Search the marketplace" data-testid={`${SHELL.searchButton}-mobile`}>
              <Search className="!size-5" />
            </Button>
          ) : (
            <button type="button" data-testid={SHELL.searchButton}
              className="flex h-11 w-full items-center gap-3 rounded-full border border-av-line bg-white px-5 text-sm text-av-muted transition-colors hover:border-av-ink/30">
              <Search className="h-4 w-4" /> Search products, vendors and categories
            </button>
          )}
        </DialogTrigger>
        <DialogContent className="rounded-2xl bg-av-linen top-[20%] translate-y-0">
          <DialogHeader>
            <DialogTitle className="font-serif text-2xl">Search AfroVending</DialogTitle>
            <DialogDescription>Full search and filters arrive in Phase 05. For now, this previews matches in development data.</DialogDescription>
          </DialogHeader>
          <form onSubmit={submit} role="search" className="flex gap-2">
            <label htmlFor="site-search" className="sr-only">Search</label>
            <Input id="site-search" autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Try “shea” or “basket”"
              className="h-11 bg-white" data-testid={SHELL.searchInput} />
            <Button type="submit" data-testid={SHELL.searchSubmit}>Search</Button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
};
