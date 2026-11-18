/**
 * 横向宠物选择 chips：当前选中橙色实底，其余白底。
 */
import { ScrollView, StyleSheet, Text, Pressable } from 'react-native';

import { clayPress, colors, hairline, radius, space, type } from '@/lib/theme';
import type { Pet } from '@/lib/types';

export function PetPicker({
  pets,
  selectedId,
  onSelect,
}: {
  pets: Pet[];
  selectedId: string | null;
  onSelect: (petId: string) => void;
}) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.row}
    >
      {pets.map((pet) => {
        const active = pet.id === selectedId;
        return (
          <Pressable
            key={pet.id}
            onPress={() => onSelect(pet.id)}
            hitSlop={4}
            style={({ pressed }) => [
              styles.chip,
              active ? styles.chipActive : styles.chipIdle,
              pressed && clayPress,
            ]}
          >
            <Text style={active ? styles.chipTextActive : styles.chipTextIdle}>
              {pet.name}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  row: {
    gap: space.sm,
    paddingVertical: 2,
  },
  chip: {
    borderRadius: radius.pill,
    borderWidth: hairline,
    paddingVertical: space.sm,
    paddingHorizontal: space.lg,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipActive: {
    backgroundColor: colors.foreground,
    borderColor: colors.foreground,
  },
  chipIdle: {
    backgroundColor: colors.card,
    borderColor: colors.border,
  },
  chipTextActive: {
    ...type.bodySm,
    color: '#FFFFFF',
    fontWeight: '700',
  },
  chipTextIdle: {
    ...type.bodySm,
    color: colors.body,
    fontWeight: '600',
  },
});
