import { ColorPicker, type ColorPickerProps } from "primereact/colorpicker";
import { cx } from "./classNames";

export const AColorPicker = ({ className, ...props }: ColorPickerProps) => (
  <ColorPicker {...props} className={cx("a-color-picker", className)} />
);
