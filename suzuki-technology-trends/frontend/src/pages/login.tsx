/**
 * ログインページ（認証機能削除版）
 * 
 * 注意: 認証機能は削除されています。
 * このページは自動的にメインページにリダイレクトします。
 * クライアント導入時にクライアントの認証機能に合わせて実装してください。
 */
import { useEffect } from 'react';
import { useRouter } from 'next/router';

export default function Login() {
  const router = useRouter();

  useEffect(() => {
    // 認証機能が削除されているため、直接メインページにリダイレクト
    router.push('/analysis/new');
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100">
      <div className="max-w-md w-full space-y-8 p-8 bg-white rounded-xl shadow-lg">
        <div className="flex flex-col items-center">
          {/* CADDi Drawerロゴ */}
          <div className="mb-6 flex items-center justify-center">
            <svg width="48" height="48" viewBox="0 0 48 48" className="text-caddi-blue">
              <path d="M12 24 L24 12 L36 24 L24 36 Z" fill="white" stroke="#2563eb" strokeWidth="2"/>
              <path d="M24 12 L36 24 L36 36 L24 24 Z" fill="#e0e7ff" stroke="#2563eb" strokeWidth="2"/>
              <path d="M12 24 L24 12 L24 24 L12 36 Z" fill="#2563eb" stroke="#2563eb" strokeWidth="2"/>
              <circle cx="24" cy="12" r="2" fill="#2563eb"/>
              <circle cx="36" cy="24" r="2" fill="#2563eb"/>
              <circle cx="12" cy="24" r="2" fill="#2563eb"/>
              <circle cx="24" cy="24" r="2" fill="#2563eb"/>
            </svg>
            <div className="ml-3">
              <h1 className="text-2xl font-bold">
                <span className="text-gray-800">CADDi</span>
                <span className="text-caddi-blue"> Drawer</span>
              </h1>
            </div>
          </div>
          <p className="text-center text-gray-600">
            リダイレクト中...
          </p>
          <div className="mt-4 animate-spin rounded-full h-8 w-8 border-b-2 border-caddi-blue"></div>
        </div>
      </div>
    </div>
  );
}

