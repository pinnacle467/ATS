import { useParams } from 'react-router-dom';
import { setTenantSlug } from '@/lib/tenant';

/**
 * Wraps every slug-prefixed route (/:slug/login, /:slug/careers...) and pins the
 * workspace slug BEFORE children mount, so their first API call already carries
 * the X-Tenant-Slug header.
 */
export default function TenantGate({ children }) {
  const { slug } = useParams();
  setTenantSlug(slug);
  return children;
}
