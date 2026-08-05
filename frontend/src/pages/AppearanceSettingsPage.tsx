import { primeThemePresets, useAppearance } from "../app/appearance";
import {
  AButton,
  ACard,
  ACheckbox,
  AColorPicker,
  AInfo,
  ALabel,
  ASelect,
} from "../components/ui";

const presetOptions = Object.keys(primeThemePresets);
export function AppearanceSettingsPage() {
  const appearance = useAppearance();
  return (
    <ACard title="Görünüm">
      <div className="grid max-w-xl gap-4">
        <AInfo title="PrimeReact theme builder">
          Preset, renk ve yüzey seçimleri bu tarayıcıda kalıcıdır. Birincil ve
          ikincil renkler Cortex bileşenleri ile PrimeReact düğmelerinde
          kullanılır.
        </AInfo>
        <ALabel>
          PrimeReact preset
          <ASelect
            value={appearance.preset}
            options={presetOptions}
            onChange={(event) => appearance.update({ preset: event.value })}
          />
        </ALabel>
        <ALabel>
          Tema
          <ASelect
            value={appearance.mode}
            options={["light", "dark", "system"]}
            onChange={(event) => appearance.update({ mode: event.value })}
          />
        </ALabel>
        <ALabel>
          Birincil renk
          <AColorPicker
            aria-label="Birincil renk"
            value={appearance.primary.replace("#", "")}
            onChange={(event) =>
              appearance.update({ primary: `#${event.value}` })
            }
          />
        </ALabel>
        <ALabel>
          İkincil renk
          <AColorPicker
            aria-label="İkincil renk"
            value={appearance.secondary.replace("#", "")}
            onChange={(event) =>
              appearance.update({ secondary: `#${event.value}` })
            }
          />
        </ALabel>
        <div className="theme-preview" aria-label="Tema önizlemesi">
          <span>Önizleme</span>
          <AButton label="Birincil eylem" />
          <AButton label="İkincil eylem" severity="secondary" />
        </div>
        <ALabel>
          Yüzey paleti
          <ASelect
            value={appearance.surface}
            options={["slate", "zinc"]}
            onChange={(event) => appearance.update({ surface: event.value })}
          />
        </ALabel>
        <ALabel>
          Köşe yarıçapı
          <ASelect
            value={appearance.radius}
            options={["sm", "md", "lg"]}
            onChange={(event) => appearance.update({ radius: event.value })}
          />
        </ALabel>
        <ALabel>
          Yoğunluk
          <ASelect
            value={appearance.density}
            options={["compact", "comfortable"]}
            onChange={(event) => appearance.update({ density: event.value })}
          />
        </ALabel>
        <ALabel>
          Yazı ölçeği
          <ASelect
            value={appearance.fontScale}
            options={["sm", "md", "lg"]}
            onChange={(event) => appearance.update({ fontScale: event.value })}
          />
        </ALabel>
        <div className="flex items-center gap-2">
          <ACheckbox
            inputId="appearance-animations"
            checked={appearance.animations}
            onChange={(event) =>
              appearance.update({ animations: Boolean(event.checked) })
            }
          />
          <ALabel className="a-label--inline" htmlFor="appearance-animations">Animasyonlar</ALabel>
        </div>
        <AButton
          label="Varsayılan görünümü geri yükle"
          outlined
          onClick={appearance.reset}
        />
      </div>
    </ACard>
  );
}
