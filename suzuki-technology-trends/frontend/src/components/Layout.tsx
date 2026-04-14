/**
 * レイアウトコンポーネント
 *
 * 注意: 認証機能は削除されています。
 * クライアント導入時にクライアントの認証機能に合わせて実装してください。
 */
import { ReactNode } from 'react';

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen bg-gray-50">
      <main>{children}</main>
    </div>
  );
}
