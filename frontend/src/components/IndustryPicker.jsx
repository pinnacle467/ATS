import { useEffect, useState } from 'react';
import { Check, Plus, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command';
import { api } from '@/lib/api';

// Module-level cache — the taxonomy rarely changes within a session, so every
// consumer of useIndustryOptions() shares one fetch instead of re-requesting
// on every mount (profile page, filter bar, add-candidate drafts, etc.)
let _cachedIndustries = null;

export function useIndustryOptions() {
  const [options, setOptions] = useState(_cachedIndustries || []);
  useEffect(() => {
    if (_cachedIndustries) return;
    api
      .get('/candidates/meta/industries')
      .then((r) => {
        _cachedIndustries = r.data.industries || [];
        setOptions(_cachedIndustries);
      })
      .catch(() => {});
  }, []);
  return options;
}

/**
 * Chip editor for a candidate's Industry field: shows current tags with a
 * remove (x) button + an "Add industry" popover (searchable list + create-new
 * affordance) so recruiters can add/remove/correct without typing free text.
 */
export function IndustryTagEditor({ value = [], onChange, testId = 'industry' }) {
  const options = useIndustryOptions();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');

  const add = (v) => {
    const clean = (v || '').trim();
    if (!clean) return;
    if (value.some((x) => x.toLowerCase() === clean.toLowerCase())) return;
    onChange([...value, clean]);
    setSearch('');
  };
  const remove = (v) => onChange(value.filter((x) => x !== v));

  const filtered = options.filter(
    (o) => o.toLowerCase().includes(search.toLowerCase()) && !value.some((v) => v.toLowerCase() === o.toLowerCase()),
  );
  const exactMatch = options.some((o) => o.toLowerCase() === search.trim().toLowerCase());

  return (
    <div className="space-y-2" data-testid={`${testId}-editor`}>
      <div className="flex flex-wrap gap-1.5">
        {value.length === 0 && <span className="text-sm text-muted-foreground">No industries tagged</span>}
        {value.map((v) => (
          <Badge key={v} variant="secondary" className="text-xs gap-1 pr-1" data-testid={`${testId}-chip-${v}`}>
            {v}
            <button
              type="button"
              onClick={() => remove(v)}
              className="hover:text-destructive ml-0.5"
              aria-label={`Remove ${v}`}
              data-testid={`${testId}-chip-remove-${v}`}
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
      </div>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" size="sm" className="h-7 text-xs" data-testid={`${testId}-add-button`}>
            <Plus className="h-3 w-3 mr-1" /> Add industry
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-64 p-0" align="start">
          <Command shouldFilter={false}>
            <CommandInput
              placeholder="Search or add industry..."
              value={search}
              onValueChange={setSearch}
              data-testid={`${testId}-search-input`}
            />
            <CommandList>
              <CommandEmpty className="px-3 py-3 text-xs text-muted-foreground">
                {search.trim() ? (
                  <button
                    type="button"
                    className="flex items-center gap-1.5 text-primary hover:underline"
                    onClick={() => { add(search); setOpen(false); }}
                    data-testid={`${testId}-create-new`}
                  >
                    <Plus className="h-3 w-3" /> Add &quot;{search.trim()}&quot;
                  </button>
                ) : 'No industries found'}
              </CommandEmpty>
              <CommandGroup>
                {filtered.slice(0, 30).map((o) => (
                  <CommandItem key={o} onSelect={() => { add(o); setOpen(false); }} data-testid={`${testId}-option-${o}`}>
                    {o}
                  </CommandItem>
                ))}
                {search.trim() && !exactMatch && filtered.length > 0 && (
                  <CommandItem onSelect={() => { add(search); setOpen(false); }} className="text-primary" data-testid={`${testId}-create-new-alt`}>
                    <Plus className="h-3 w-3 mr-1" /> Add &quot;{search.trim()}&quot;
                  </CommandItem>
                )}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}

/**
 * Read-only display of a candidate's industries as compact chips. Shows the
 * first `max` tags plus a "+N more" toggle so the profile page doesn't get
 * cluttered when a candidate has many industries tagged.
 */
export function IndustryChips({ industries = [], max = 4, testId = 'industry-chips' }) {
  const [expanded, setExpanded] = useState(false);
  if (!industries.length) return <span className="text-muted-foreground text-sm">No industries tagged</span>;
  const shown = expanded ? industries : industries.slice(0, max);
  const remaining = industries.length - shown.length;
  return (
    <div className="flex flex-wrap gap-1.5" data-testid={testId}>
      {shown.map((v) => (
        <Badge key={v} variant="outline" className="text-xs bg-accent/50 border-accent" data-testid={`${testId}-tag-${v}`}>{v}</Badge>
      ))}
      {remaining > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="text-xs text-primary hover:underline"
          data-testid={`${testId}-more`}
        >
          +{remaining} more
        </button>
      )}
    </div>
  );
}

/**
 * Filter-bar dropdown: searchable checkbox multi-select over the industry
 * taxonomy. Selected values are OR'd together server-side.
 */
export function IndustryFilterMenu({ value = [], onChange }) {
  const options = useIndustryOptions();
  const [open, setOpen] = useState(false);
  const toggle = (o) => onChange(value.includes(o) ? value.filter((x) => x !== o) : [...value, o]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="h-9 gap-1.5"
          data-testid="candidates-filter-industry-button"
        >
          Industry
          {value.length > 0 && <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">{value.length}</Badge>}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-0" align="start">
        <Command>
          <CommandInput placeholder="Search industries..." data-testid="candidates-filter-industry-search" />
          <CommandList>
            <CommandEmpty className="px-3 py-3 text-xs text-muted-foreground">No match</CommandEmpty>
            <CommandGroup>
              {options.map((o) => (
                <CommandItem key={o} onSelect={() => toggle(o)} data-testid={`candidates-filter-industry-option-${o}`}>
                  <div className={`h-4 w-4 rounded-sm border flex items-center justify-center mr-2 shrink-0 ${value.includes(o) ? 'bg-primary border-primary' : 'border-input'}`}>
                    {value.includes(o) && <Check className="h-3 w-3 text-primary-foreground" />}
                  </div>
                  {o}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
        {value.length > 0 && (
          <div className="border-t border-border p-2">
            <Button variant="ghost" size="sm" className="w-full h-7 text-xs" onClick={() => onChange([])} data-testid="candidates-filter-industry-clear">
              Clear industries
            </Button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
