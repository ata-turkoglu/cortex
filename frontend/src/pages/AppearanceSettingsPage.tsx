import { useAppearance } from "../app/appearance";
import { ACard, ASelect } from "../ui/primitives";
export function AppearanceSettingsPage() {
  const appearance = useAppearance();
  return (
    <ACard title="Görünüm">
      <div className="grid max-w-xl gap-4">
        <label>
          Tema
          <ASelect
            value={appearance.mode}
            options={["light", "dark", "system"]}
            onChange={(event) => appearance.update({ mode: event.value })}
          />
        </label>
        <label>
          Birincil renk
          <input
            aria-label="Birincil renk"
            type="color"
            value={appearance.primary}
            onChange={(event) =>
              appearance.update({ primary: event.target.value })
            }
          />
        </label>
        <label>
          Yazı ölçeği
          <ASelect
            value={appearance.fontScale}
            options={["sm", "md", "lg"]}
            onChange={(event) => appearance.update({ fontScale: event.value })}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={appearance.animations}
            onChange={(event) =>
              appearance.update({ animations: event.target.checked })
            }
          />{" "}
          Animasyonlar
        </label>
      </div>
    </ACard>
  );
}
