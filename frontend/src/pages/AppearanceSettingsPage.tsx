import { primeThemePresets, useAppearance } from "../app/appearance";
import { AButton, ACard, AInfo, ASelect } from "../ui/primitives";

const presetOptions = Object.keys(primeThemePresets);
export function AppearanceSettingsPage() {
  const appearance = useAppearance();
  return (
    <ACard title="Görünüm">
      <div className="grid max-w-xl gap-4">
        <AInfo title="PrimeReact theme builder">
          Preset, renk ve yüzey seçimleri bu tarayıcıda kalıcıdır. Birincil ve ikincil
          renkler Cortex bileşenleri ile PrimeReact düğmelerinde kullanılır.
        </AInfo>
        <label>
          PrimeReact preset
          <ASelect
            value={appearance.preset}
            options={presetOptions}
            onChange={(event) => appearance.update({ preset: event.value })}
          />
        </label>
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
          İkincil renk
          <input
            aria-label="İkincil renk"
            type="color"
            value={appearance.secondary}
            onChange={(event) => appearance.update({ secondary: event.target.value })}
          />
        </label>
        <div className="theme-preview" aria-label="Tema önizlemesi">
          <span>Önizleme</span>
          <AButton label="Birincil eylem" />
          <AButton label="İkincil eylem" severity="secondary" />
        </div>
        <label>
          Yüzey paleti
          <ASelect
            value={appearance.surface}
            options={["slate", "zinc"]}
            onChange={(event) => appearance.update({ surface: event.value })}
          />
        </label>
        <label>
          Köşe yarıçapı
          <ASelect
            value={appearance.radius}
            options={["sm", "md", "lg"]}
            onChange={(event) => appearance.update({ radius: event.value })}
          />
        </label>
        <label>
          Yoğunluk
          <ASelect
            value={appearance.density}
            options={["compact", "comfortable"]}
            onChange={(event) => appearance.update({ density: event.value })}
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
        <AButton label="Varsayılan görünümü geri yükle" outlined onClick={appearance.reset} />
      </div>
    </ACard>
  );
}
