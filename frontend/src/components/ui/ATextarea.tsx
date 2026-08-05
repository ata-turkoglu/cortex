import { InputTextarea, type InputTextareaProps } from "primereact/inputtextarea";
import { cx } from "./classNames";
export const ATextarea = ({ className, rows = 8, ...props }: InputTextareaProps) => <InputTextarea {...props} rows={rows} className={cx("a-textarea", className)} />;
