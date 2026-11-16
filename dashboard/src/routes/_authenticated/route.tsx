import { createFileRoute, redirect } from '@tanstack/react-router'
import { syncAuthFromSession } from '@/stores/auth-store'
import { supabase } from '@/lib/supabase'
import { AuthenticatedLayout } from '@/components/layout/authenticated-layout'

export const Route = createFileRoute('/_authenticated')({
  beforeLoad: async () => {
    const { data } = await supabase.auth.getSession()
    if (!data.session) {
      throw redirect({ to: '/sign-up' })
    }
    await syncAuthFromSession()
    // Fire welcome email once per user (magic link confirmation)
    const welcomeKey = `welcome_sent_${data.session.user.email}`
    if (!localStorage.getItem(welcomeKey)) {
      localStorage.setItem(welcomeKey, '1')
      fetch('https://web-production-6adc6.up.railway.app/send-welcome', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: data.session.user.email,
          product_name: (import.meta.env.VITE_PRODUCT_NAME as string),
          dashboard_url: window.location.origin,
        }),
      }).catch(() => {})
    }
  },
  component: AuthenticatedLayout,
})
