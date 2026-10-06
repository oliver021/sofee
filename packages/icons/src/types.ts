/** design-system.md §6: "Icon: 20px, currentColor, 1.6 stroke, round caps and joins." Every
 * icon in this package shares this one prop — colour and sizing context (hover/active state,
 * the 44x44 target) belong to the wrapping IconButton in @sofee/ui, not to the icon itself. */
export interface IconProps {
  size?: number;
}
