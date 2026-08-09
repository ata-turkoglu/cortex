import { Button, type ButtonProps } from "primereact/button";
import { AIcon, type IconName } from "../../icons/AIcon";
import { cx } from "./classNames";
export type AButtonProps = Omit<ButtonProps, "icon"> & { icon?: IconName };
export const AButton = ({
  icon,
  className,
  severity,
  outlined,
  ...props
}: AButtonProps) => (
  <Button
    {...props}
    className={cx("a-button", className)}
    icon={icon ? <AIcon name={icon} size={16} /> : undefined}
    severity={severity}
    outlined={outlined ?? severity === "secondary"}
  />
);
