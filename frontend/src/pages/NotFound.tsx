import React from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/lib/i18n';
import { Home, AlertTriangle } from 'lucide-react';

const NotFound: React.FC = () => {
  const { t } = useLanguage();
  const tt = (key: string, fallback: string) => {
    const v = t(key);
    return v === key ? fallback : v;
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center px-4">
        <div className="mx-auto w-20 h-20 bg-card rounded-full flex items-center justify-center mb-6 border border-border">
          <AlertTriangle className="h-10 w-10 text-warning" />
        </div>
        <h1 className="text-6xl font-bold text-foreground mb-2">404</h1>
        <p className="text-xl text-muted-foreground mb-8">{tt('page_not_found', 'Page Not Found')}</p>
        <p className="text-muted-foreground mb-8 max-w-md mx-auto">
          {tt('page_not_found_desc', 'The page you are looking for does not exist or has been moved.')}
        </p>
        <Button asChild>
          <Link to="/">
            <Home className="h-5 w-5" />
            {tt('back_home', 'Back Home')}
          </Link>
        </Button>
      </div>
    </div>
  );
};

export default NotFound;
