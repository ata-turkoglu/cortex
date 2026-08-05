import { useId, useState, type ChangeEvent, type InputHTMLAttributes } from "react";
import { cx } from "./classNames";
export function AFileUpload({ chooseLabel = "Dosya seç", emptyLabel = "Dosya seçilmedi", multipleSelectedLabel, className, onChange, ...props }: InputHTMLAttributes<HTMLInputElement> & { chooseLabel?: string; emptyLabel?: string; multipleSelectedLabel?: (count: number) => string }) {
  const inputId = useId(); const [fileNames, setFileNames] = useState<string[]>([]);
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => { const files = Array.from(event.target.files ?? []); setFileNames(files.map((file) => file.name)); onChange?.(event); };
  const selectionLabel = fileNames.length === 0 ? emptyLabel : fileNames.length === 1 ? fileNames[0] : multipleSelectedLabel?.(fileNames.length) ?? `${fileNames.length} dosya seçildi`;
  return <div className={cx("a-file-upload", className)}><input {...props} id={inputId} type="file" className="a-file-upload__native" onChange={handleChange} /><label htmlFor={inputId} className="a-file-upload__button">{chooseLabel}</label><span className="a-file-upload__selection" title={fileNames.join(", ")}>{selectionLabel}</span></div>;
}
