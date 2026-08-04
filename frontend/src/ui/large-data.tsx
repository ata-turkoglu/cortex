import { useMemo, useState, type ReactNode, type UIEvent } from "react";
import { APaginator, ATable } from "./primitives";
export type PageState = {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
};
export function AServerTable({
  value,
  page,
  children,
}: {
  value: Record<string, unknown>[];
  page: PageState;
  children: ReactNode;
}) {
  const pages = Math.max(1, Math.ceil(page.total / page.pageSize));
  return (
    <>
      <ATable value={value}>{children}</ATable>
      <APaginator>
        <div className="mt-3 flex gap-2 text-sm">
          <button
            disabled={page.page === 0}
            onClick={() => page.onPageChange(page.page - 1)}
          >
            Previous
          </button>
          <span>
            Page {page.page + 1} / {pages}
          </span>
          <button
            disabled={page.page + 1 >= pages}
            onClick={() => page.onPageChange(page.page + 1)}
          >
            Next
          </button>
        </div>
      </APaginator>
    </>
  );
}
export function AVirtualList<T>({
  items,
  renderItem,
  rowHeight = 40,
  viewportHeight = 384,
}: {
  items: T[];
  renderItem: (item: T, index: number) => ReactNode;
  rowHeight?: number;
  viewportHeight?: number;
}) {
  const [scrollTop, setScrollTop] = useState(0);
  const { start, end } = useMemo(() => {
    const visibleRows = Math.ceil(viewportHeight / rowHeight);
    const overscan = 5;
    const first = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
    return { start: first, end: Math.min(items.length, first + visibleRows + overscan * 2) };
  }, [items.length, rowHeight, scrollTop, viewportHeight]);
  const onScroll = (event: UIEvent<HTMLDivElement>) => setScrollTop(event.currentTarget.scrollTop);
  return (
    <div
      role="list"
      className="overflow-auto"
      style={{ height: viewportHeight }}
      onScroll={onScroll}
    >
      <div style={{ height: items.length * rowHeight, position: "relative" }}>
        {items.slice(start, end).map((item, relativeIndex) => {
          const index = start + relativeIndex;
          return (
            <div
              role="listitem"
              key={index}
              style={{ height: rowHeight, left: 0, position: "absolute", right: 0, top: index * rowHeight }}
            >
              {renderItem(item, index)}
            </div>
          );
        })}
      </div>
    </div>
  );
}
