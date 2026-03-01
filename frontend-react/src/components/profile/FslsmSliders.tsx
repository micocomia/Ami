import { cn } from '@/lib/cn';
import type { AppConfig } from '@/types';

const FSLSM_DIMS = [
  { key: 'fslsm_processing', label: 'Processing' },
  { key: 'fslsm_perception', label: 'Perception' },
  { key: 'fslsm_input', label: 'Input' },
  { key: 'fslsm_understanding', label: 'Understanding' },
] as const;

interface FslsmSlidersProps {
  values: Record<string, number>;
  config?: AppConfig;
  onChange?: (dim: string, value: number) => void;
}

export function FslsmSliders({ values, config, onChange }: FslsmSlidersProps) {
  return (
    <div className="space-y-4">
      {FSLSM_DIMS.map(({ key, label }) => {
        const val = typeof values[key] === 'number' ? values[key] : 0;
        const dimConfig = config?.fslsm_thresholds?.[key];
        const lowLabel = dimConfig?.low_label ?? 'Active';
        const highLabel = dimConfig?.high_label ?? 'Reflective';
        const neutralLabel = dimConfig?.neutral_label ?? 'Balanced';
        const pct = ((val + 1) / 2) * 100;

        const displayLabel =
          Math.abs(val) < 0.1
            ? neutralLabel
            : val < 0
            ? lowLabel
            : highLabel;

        return (
          <div key={key} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500">{label}</span>
              <span className="font-medium text-slate-700">{displayLabel}</span>
            </div>
            <div className="flex items-center gap-2 text-[10px] text-slate-400">
              <span className="w-16 text-right shrink-0">{lowLabel}</span>
              {onChange ? (
                <input
                  type="range"
                  min={-1}
                  max={1}
                  step={0.1}
                  value={val}
                  onChange={(e) => onChange(key, parseFloat(e.target.value))}
                  className="flex-1 h-1.5 accent-primary-600"
                />
              ) : (
                <div className="relative flex-1 h-1.5 bg-slate-200 rounded-full">
                  <div
                    className={cn(
                      'absolute top-0 h-full rounded-full',
                      val < 0 ? 'bg-primary-400 right-1/2' : 'bg-primary-500 left-1/2',
                    )}
                    style={{ width: `${Math.abs(val) * 50}%` }}
                  />
                  <div
                    className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-primary-600 border-2 border-white shadow"
                    style={{ left: `${pct}%`, transform: 'translate(-50%, -50%)' }}
                  />
                </div>
              )}
              <span className="w-16 shrink-0">{highLabel}</span>
            </div>
            <div className="text-right text-[10px] text-slate-400">{val.toFixed(2)}</div>
          </div>
        );
      })}
    </div>
  );
}
