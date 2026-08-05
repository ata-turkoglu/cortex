export const cx = (...classes: Array<string | undefined | false>) =>
  classes.filter(Boolean).join(" ");
