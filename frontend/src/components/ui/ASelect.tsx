import { Dropdown, type DropdownProps } from "primereact/dropdown";
import { cx } from "./classNames";
export const ASelect = ({ className, panelClassName, ...props }: DropdownProps) => <Dropdown {...props} className={cx("a-select", className)} panelClassName={cx("a-select-panel", panelClassName)} />;
