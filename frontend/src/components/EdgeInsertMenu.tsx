import { useTranslation } from "react-i18next";
import {
  INSERTABLE_ACTION_TYPES,
  INSERTABLE_FLOW_TYPES,
  insertPaletteNodeAtSelection,
  type PaletteNodeType,
} from "@/inspector/insertFlowNode";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface Props {
  edgeId: string;
  children: React.ReactNode;
}

export function EdgeInsertMenu({ edgeId, children }: Props) {
  const { t } = useTranslation();
  const entries: PaletteNodeType[] = [
    ...INSERTABLE_ACTION_TYPES,
    ...INSERTABLE_FLOW_TYPES,
  ];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{children}</DropdownMenuTrigger>
      <DropdownMenuContent align="center" className="max-h-72 w-44 overflow-y-auto">
        <DropdownMenuLabel className="text-[10px] uppercase tracking-wide">
          {t("graph.insertOnEdge")}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {entries.map((entry) => (
          <DropdownMenuItem
            key={entry.type}
            className="text-xs"
            onSelect={() =>
              insertPaletteNodeAtSelection(
                entry,
                t(`nodePalette.${entry.labelKey}`),
                edgeId,
              )
            }
          >
            {t(`nodePalette.${entry.labelKey}`)}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
