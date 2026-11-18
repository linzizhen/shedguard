/**
 * 把相册/相机给出的地址变成可以上传的 multipart 表单。
 *
 * 两端的差异必须在这里吃掉：
 * - 原生（iOS/Android）的 `FormData` 认 `{ uri, name, type }` 这种描述对象；
 * - 网页端（react-native-web）的 `FormData` 只认真正的 `Blob`/`File`，
 *   直接把 `{ uri }` 塞进去会被序列化成 `[object Object]`，服务端只会回 400。
 */
import { Platform } from 'react-native';

const MAX_CLIENT_BYTES = 10 * 1024 * 1024;

export class PhotoTooLargeError extends Error {
  constructor() {
    super('这张照片太大了（超过 10 MB），换一张小一点的，或者用手机自带的编辑功能裁一下。');
    this.name = 'PhotoTooLargeError';
  }
}

export async function buildPhotoForm(uri: string, name = 'check.jpg'): Promise<FormData> {
  const form = new FormData();

  if (Platform.OS === 'web') {
    const response = await fetch(uri);
    const blob = await response.blob();
    if (blob.size > MAX_CLIENT_BYTES) {
      throw new PhotoTooLargeError();
    }
    form.append('file', blob, name);
    return form;
  }

  form.append('file', { uri, name, type: 'image/jpeg' } as unknown as Blob);
  return form;
}