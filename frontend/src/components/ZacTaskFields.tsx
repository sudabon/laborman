import { salesItemLabel, salesItemsOf } from "@/lib/zacDefaults";
import type { ZacSalesItem, ZacWorkKind } from "@/types";

const selectClass =
  "h-10 w-full rounded-md border border-input bg-card px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60";

type ZacTaskFieldsProps = {
  idPrefix: string;
  jobCode: string;
  salesItems: ZacSalesItem[];
  workKinds: ZacWorkKind[];
  salesItemId: string;
  workKind: string;
  onSalesItemChange: (id: string) => void;
  onWorkKindChange: (name: string) => void;
};

/** タスクの zac の売上項目・作業内容の選択欄。売上項目はジョブの選択肢だけを出す。 */
export function ZacTaskFields({
  idPrefix,
  jobCode,
  salesItems,
  workKinds,
  salesItemId,
  workKind,
  onSalesItemChange,
  onWorkKindChange,
}: ZacTaskFieldsProps) {
  const items = salesItemsOf(jobCode, salesItems, salesItemId);
  const kinds = workKinds.filter((kind) => kind.is_active || kind.name === workKind);
  return (
    <>
      <div className="grid gap-1">
        <label htmlFor={`${idPrefix}-sales-item`} className="text-sm font-medium">
          売上項目
        </label>
        <select
          id={`${idPrefix}-sales-item`}
          className={selectClass}
          value={salesItemId}
          disabled={!jobCode || items.length === 0}
          onChange={(event) => onSalesItemChange(event.target.value)}
        >
          <option value="">{jobCode && items.length === 0 ? "（売上項目が未登録）" : "（未選択）"}</option>
          {items.map((item) => (
            <option key={item.id} value={item.id}>
              {salesItemLabel(item)}
            </option>
          ))}
        </select>
      </div>
      <div className="grid gap-1">
        <label htmlFor={`${idPrefix}-work-kind`} className="text-sm font-medium">
          作業内容
        </label>
        <select
          id={`${idPrefix}-work-kind`}
          className={selectClass}
          value={workKind}
          onChange={(event) => onWorkKindChange(event.target.value)}
        >
          <option value="">（未選択）</option>
          {kinds.map((kind) => (
            <option key={kind.name} value={kind.name}>
              {kind.name}
            </option>
          ))}
        </select>
      </div>
    </>
  );
}
