import { DataTable, type DataTableProps, type DataTableValueArray } from "primereact/datatable";
import { cx } from "./classNames";
export function ATable<TValue extends DataTableValueArray>({ className, ...props }: DataTableProps<TValue>) { return <DataTable {...props} className={cx("a-table", className)} />; }
