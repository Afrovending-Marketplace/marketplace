import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Search, Store, Tag, LayoutGrid } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { SHELL } from "@/constants/testIds";
import { formatPrice } from "@/lib/catalog";
import { getSuggestions } from "@/lib/search";
import { cn } from "@/lib/utils";

const useSuggestions = (q) => {
  const [s, setS] = useState(null);
  useEffect(() => {
    if (q.trim().length < 2) {
      setS(null);
      return undefined;
    }
    const t = setTimeout(() => { getSuggestions(q.trim()).then(setS).catch(() => setS(null)); }, 200);
    return () => clearTimeout(t);
  }, [q]);
  return s;
};

const Item = ({ to, icon: Icon, children, testId, onPick }) => (
  <li><Link to={to} onClick={onPick} data-testid={testId} className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm hover:bg-av-sand">
    <Icon className="h-4 w-4 shrink-0 text-av-muted" /><span className="flex-1 truncate">{children}</span></Link></li>
);

const Suggestions = ({ s, onPick }) => {
  if (!s) return null;
  const none = !s.keywords.length && !s.products.length && !s.categories.length && !s.vendors.length;
  if (none) return <p className="px-3 py-2 text-sm text-av-muted" data-testid="suggest-none">No suggestions — press Enter to search all products.</p>;
  return (
    <ul className="max-h-80 overflow-y-auto py-1" data-testid="search-suggestions" role="listbox">
      {s.keywords.map((k) => <Item key={`k-${k}`} to={`/search?q=${encodeURIComponent(k)}`} icon={Search} testId={`suggest-keyword-${k}`} onPick={onPick}>{k}</Item>)}
      {s.products.map((p) => <Item key={p.slug} to={`/products/${p.slug}`} icon={Tag} testId={`suggest-product-${p.slug}`} onPick={onPick}>{p.title} <span className="text-av-muted">· {formatPrice(p.price_minor, p.currency)}</span></Item>)}
      {s.categories.map((c) => <Item key={c.slug} to={`/categories/${c.slug}`} icon={LayoutGrid} testId={`suggest-category-${c.slug}`} onPick={onPick}>{c.name} <span className="text-av-muted">· category</span></Item>)}
      {s.vendors.map((v) => <Item key={v.slug} to={`/vendors/${v.slug}`} icon={Store} testId={`suggest-vendor-${v.slug}`} onPick={onPick}>{v.name} <span className="text-av-muted">· vendor</span></Item>)}
    </ul>
  );
};

export const SearchBox = ({ initial = "", onDone, autoFocus, testPrefix = "site-search" }) => {
  const [q, setQ] = useState(initial);
  const [open, setOpen] = useState(false);
  const s = useSuggestions(open ? q : "");
  const navigate = useNavigate();
  const box = useRef(null);
  const submit = (e) => {
    e.preventDefault();
    setOpen(false);
    onDone?.();
    navigate(q.trim() ? `/search?q=${encodeURIComponent(q.trim())}` : "/shop");
  };
  return (
    <div ref={box} className="relative" onBlur={(e) => !box.current?.contains(e.relatedTarget) && setOpen(false)}>
      <form onSubmit={submit} role="search" className="flex gap-2">
        <label htmlFor={`${testPrefix}-input`} className="sr-only">Search</label>
        <Input id={`${testPrefix}-input`} autoFocus={autoFocus} autoComplete="off" value={q} maxLength={100} onFocus={() => setOpen(true)}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }} placeholder="Try “shea”, “kente” or “basket”"
          className="h-11 bg-white" data-testid={testPrefix === "site-search" ? SHELL.searchInput : `${testPrefix}-input`} />
        <Button type="submit" data-testid={testPrefix === "site-search" ? SHELL.searchSubmit : `${testPrefix}-submit`}>Search</Button>
      </form>
      {open && s && <div className={cn("z-30 mt-2 rounded-xl border border-av-line bg-white shadow-lg", testPrefix !== "site-search" && "absolute inset-x-0")}>
        <Suggestions s={s} onPick={() => { setOpen(false); onDone?.(); }} /></div>}
    </div>
  );
};

export const SearchEntry = ({ compact = false, className }) => {
  const [open, setOpen] = useState(false);
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
        <DialogContent className="rounded-2xl bg-av-linen top-[15%] translate-y-0">
          <DialogHeader>
            <DialogTitle className="font-serif text-2xl">Search AfroVending</DialogTitle>
            <DialogDescription>Search products, tags, categories and vendors.</DialogDescription>
          </DialogHeader>
          <SearchBox autoFocus onDone={() => setOpen(false)} />
        </DialogContent>
      </Dialog>
    </div>
  );
};
