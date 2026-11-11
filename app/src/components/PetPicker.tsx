/**
 * 横向宠物选择 chips：当前选中橙色实底，其余白底。
 */
import { ScrollView, StyleSheet, Text, Pressable } from 'react-native';

import { clayPress, colors, radius } from '@/lib/theme';
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
    gap: 8,
    paddingVertical: 2,
  },
  chip: {
    borderRadius: radius.md,
    borderWidth: 3,
    paddingVertical: 8,
    paddingHorizontal: 16,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primaryDark,
  },
  chipIdle: {
    backgroundColor: colors.card,
    borderColor: colors.border,
  },
  chipTextActive: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '700',
  },
  chipTextIdle: {
    color: colors.foreground,
    fontSize: 14,
    fontWeight: '600',
  },
});
