import { useSearchParams } from "react-router-dom";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SORTS } from "@/lib/catalog";

export const useSort = () => {
  const [params, setParams] = useSearchParams();
  const sort = params.get("sort") || "featured";
  const setSort = (v) => {
    const next = new URLSearchParams(params);
    next.set("sort", v);
    setParams(next, { replace: true });
  };
  return [sort, setSort];
};

export const SortSelect = ({ value, onChange, count }) => (
  <div className="flex items-center justify-between gap-4 border-b border-av-line pb-4">
    <p data-testid="listing-result-count" className="text-sm text-av-muted">{count} {count === 1 ? "item" : "items"}</p>
    <div className="flex items-center gap-2">
      <label htmlFor="listing-sort" className="text-sm text-av-muted">Sort</label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id="listing-sort" data-testid="listing-sort-select" className="h-10 w-48 rounded-full bg-white"><SelectValue /></SelectTrigger>
        <SelectContent>
          {SORTS.map(([v, l]) => <SelectItem key={v} value={v} data-testid={`listing-sort-${v}`}>{l}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  </div>
);
