import React from 'react';
import NotFoundState from '@/components/states/NotFoundState';

/** Route-level 404 (`path="*"`) — thin wrapper over the shared takeover. */
const NotFound: React.FC = () => <NotFoundState />;

export default NotFound;
