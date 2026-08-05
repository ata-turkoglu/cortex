import { InputText, type InputTextProps } from "primereact/inputtext";
import { cx } from "./classNames";
export const AInput = ({ className, ...props }: InputTextProps) => <InputText {...props} className={cx("a-input", className)} />;
