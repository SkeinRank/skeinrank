import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";

import type { CanonicalTerm } from "../types";
import { Badge } from "./ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";

const columns: ColumnDef<CanonicalTerm>[] = [
  {
    accessorKey: "canonical_value",
    header: "Canonical value",
    cell: ({ row }) => <span className="font-medium text-slate-950 dark:text-slate-50">{row.original.canonical_value}</span>,
  },
  {
    accessorKey: "slot",
    header: "Slot",
    cell: ({ row }) => <Badge>{row.original.slot}</Badge>,
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <span className="text-sm capitalize text-slate-600 dark:text-slate-300">{row.original.status}</span>,
  },
  {
    id: "aliases",
    header: "Aliases",
    cell: ({ row }) => (
      <div className="flex flex-wrap gap-1.5">
        {row.original.aliases.length > 0 ? (
          row.original.aliases.map((alias) => (
            <Badge key={alias.id} className="bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-200">
              {alias.alias_value}
            </Badge>
          ))
        ) : (
          <span className="text-sm text-slate-400 dark:text-slate-500">No aliases yet</span>
        )}
      </div>
    ),
  },
];

export function TermsTable({ terms }: { terms: CanonicalTerm[] }) {
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
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle>Canonical terms</CardTitle>
          <CardDescription>Search and inspect profile terms, slots, and aliases.</CardDescription>
        </div>
        <Input
          className="sm:w-72"
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Filter terms or aliases..."
          value={filter}
        />
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-hidden rounded-b-2xl">
          <table className="w-full border-collapse text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th key={header.id} className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">
                      {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.length > 0 ? (
                table.getRowModel().rows.map((row) => (
                  <tr key={row.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-950">
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-5 py-4 align-top">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-5 py-8 text-center text-sm text-slate-500 dark:text-slate-400" colSpan={columns.length}>
                    No terms found for this profile.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
