import { RadioButton } from "primereact/radiobutton";

export type ARadioProps = {
  checked: boolean;
  disabled?: boolean;
  name: string;
  onChange: () => void;
  value: string;
};

/** A Cortex-owned radio control that keeps PrimeReact event types out of feature code. */
export function ARadio({ onChange, ...props }: ARadioProps) {
  return <RadioButton {...props} onChange={onChange} />;
}
