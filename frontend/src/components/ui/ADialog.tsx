import { Dialog, type DialogProps } from "primereact/dialog";
import { cx } from "./classNames";
export const ADialog = ({ className, ...props }: DialogProps) => <Dialog {...props} className={cx("a-dialog", className)} />;
