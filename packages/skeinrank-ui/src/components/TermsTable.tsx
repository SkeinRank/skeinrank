import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { cn } from "../lib/utils";
import type { CanonicalTerm } from "../types";
import { SectionCard } from "./layout/ConsolePrimitives";
import { Badge } from "./ui/badge";
import { Input } from "./ui/input";

const columns: ColumnDef<CanonicalTerm>[] = [
  {
    accessorKey: "canonical_value",
    header: "Canonical value",
    cell: ({ row }) => (
      <div className="min-w-0">
        <span className="block truncate font-semibold text-slate-950 dark:text-slate-50">
          {row.original.canonical_value}
        </span>
        {row.original.description ? (
          <span className="mt-1 block max-w-md truncate text-xs text-slate-500 dark:text-slate-400">
            {row.original.description}
          </span>
        ) : null}
      </div>
    ),
  },
  {
    accessorKey: "slot",
    header: "Slot",
    cell: ({ row }) => <Badge>{row.original.slot}</Badge>,
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <span className="text-sm capitalize text-slate-600 dark:text-slate-300">
        {row.original.status}
      </span>
    ),
  },
  {
    id: "aliases",
    header: "Aliases",
    cell: ({ row }) => (
      <div className="flex max-w-md flex-wrap gap-1.5">
        {row.original.aliases.length > 0 ? (
          row.original.aliases.slice(0, 5).map((alias) => (
            <Badge
              key={alias.id}
              className="bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-200"
            >
              {alias.alias_value}
            </Badge>
          ))
        ) : (
          <span className="text-sm text-slate-400 dark:text-slate-500">
            No aliases yet
          </span>
        )}
        {row.original.aliases.length > 5 ? (
          <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            +{row.original.aliases.length - 5}
          </Badge>
        ) : null}
      </div>
    ),
  },
];

type TermsTableProps = {
  onSelectTerm?: (term: CanonicalTerm) => void;
  selectedTermId?: number | null;
  terms: CanonicalTerm[];
};

export function TermsTable({
  onSelectTerm,
  selectedTermId,
  terms,
}: TermsTableProps) {
  const [filter, setFilter] = useState("");
  const data = useMemo(() => terms, [terms]);

  const table = useReactTable({
    data,
    columns,
    state: {
      globalFilter: filter,
    },
    onGlobalFilterChange: setFilter,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  return (
    <SectionCard
      actions={
        <Input
          className="sm:w-72"
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Filter terms or aliases..."
          value={filter}
        />
      }
      contentClassName="p-0"
      description="Search, select, and inspect profile terms, slots, and aliases."
      title="Canonical terms"
    >
      <div className="overflow-hidden rounded-b-2xl">
        <div className="max-h-[min(52rem,calc(100vh-20rem))] overflow-auto">
          <table className="w-full min-w-[760px] border-collapse text-left text-sm">
            <thead className="sticky top-0 z-10 bg-slate-50 text-xs uppercase tracking-wide text-slate-500 shadow-[inset_0_-1px_0_rgb(226_232_240)] dark:bg-slate-950 dark:text-slate-400 dark:shadow-[inset_0_-1px_0_rgb(30_41_59)]">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th key={header.id} className="px-5 py-3 font-semibold">
                      {header.isPlaceholder
                        ? null
                        : flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.length > 0 ? (
                table.getRowModel().rows.map((row) => (
                  <tr
                    aria-selected={selectedTermId === row.original.id}
                    className={cn(
                      "cursor-pointer border-b border-slate-100 transition-colors last:border-0 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-slate-300 dark:border-slate-800 dark:hover:bg-slate-900/70 dark:focus:ring-slate-700",
                      selectedTermId === row.original.id &&
                        "bg-blue-50/80 hover:bg-blue-50 dark:bg-blue-950/30 dark:hover:bg-blue-950/30",
                    )}
                    key={row.id}
                    onClick={() => onSelectTerm?.(row.original)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelectTerm?.(row.original);
                      }
                    }}
                    tabIndex={0}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-5 py-4 align-top">
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </td>
                    ))}
                  </tr>
                ))
              ) : (
                <tr>
                  <td
                    className="px-5 py-10 text-center text-sm text-slate-500 dark:text-slate-400"
                    colSpan={columns.length}
                  >
                    No terms found for this profile.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </SectionCard>
  );
}
