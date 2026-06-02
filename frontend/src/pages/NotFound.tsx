import React from 'react';
import { Link } from 'react-router-dom';
import { useLanguage } from '@/lib/i18n';
import { Home, AlertTriangle } from 'lucide-react';

const NotFound: React.FC = () => {
  const { t } = useLanguage();

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900">
      <div className="text-center px-4">
        <div className="mx-auto w-20 h-20 bg-slate-800 rounded-full flex items-center justify-center mb-6 border border-slate-700">
          <AlertTriangle className="h-10 w-10 text-amber-400" />
        </div>
        <h1 className="text-6xl font-bold text-white mb-2">404</h1>
        <p className="text-xl text-slate-400 mb-8">Page Not Found</p>
        <p className="text-slate-500 mb-8 max-w-md mx-auto">
          The page you are looking for does not exist or has been moved.
        </p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
        >
          <Home className="h-5 w-5" />
          {t('back')} Home
        </Link>
      </div>
    </div>
  );
};

export default NotFound;