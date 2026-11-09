/**
 * 拍照查验 Tab（骨架占位）。
 * 实现计划：expo-camera 取景 → POST /api/v1/pets/{id}/check-photo → 结果卡片。
 */
import { Card, EmptyState, PageHeader, Screen } from '@/components/ui';

export default function CheckScreen() {
  return (
    <Screen>
      <PageHeader title="拍照查验" subtitle="拍一张照片，看看它是不是要蜕皮了" />
      <Card style={{ paddingVertical: 24 }}>
        <EmptyState
          icon="camera"
          title="相机功能开发中"
          subtitle="下一步接入相机与拍照查验接口，对准守宫拍一张即可判定蜕皮状态"
        />
      </Card>
    </Screen>
  );
}
