import { zodResolver } from '@hookform/resolvers/zod'
import { motion } from 'framer-motion'
import { Bot, FileSearch, ShieldCheck, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { FieldError, Input, Label } from '@/components/ui/input'
import { useAuth } from '@/context/AuthContext'

const loginSchema = z.object({
  email: z.string().email('Enter a valid work email'),
  password: z.string().min(1, 'Password is required'),
})

const registerSchema = z.object({
  fullName: z.string().max(255).optional(),
  email: z.string().email('Enter a valid work email'),
  password: z.string().min(8, 'Minimum 8 characters'),
})

const FEATURES = [
  { icon: FileSearch, text: 'OCR + parsing turns every PDF and scan into searchable knowledge' },
  { icon: Sparkles, text: 'Multi-agent RAG answers stream live with page-level citations' },
  { icon: ShieldCheck, text: 'JWT authentication, audit trail and answer-quality evaluation' },
]

export default function LoginPage() {
  const { login, register: registerAccount } = useAuth()
  const navigate = useNavigate()
  const [mode, setMode] = useState('login')          // login | register
  const [rememberMe, setRememberMe] = useState(true)
  const [serverError, setServerError] = useState('')

  const { register, handleSubmit, formState: { errors, isSubmitting }, reset } = useForm({
    resolver: zodResolver(mode === 'login' ? loginSchema : registerSchema),
  })

  const switchMode = (next) => {
    setMode(next)
    setServerError('')
    reset()
  }

  const onSubmit = async (values) => {
    setServerError('')
    try {
      if (mode === 'login') {
        await login({ ...values, rememberMe })
      } else {
        await registerAccount(values)
      }
      navigate('/', { replace: true })
    } catch (err) {
      setServerError(err.message)
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Brand panel */}
      <div className="relative hidden flex-1 items-center justify-center overflow-hidden bg-gradient-to-br from-[#0f1420] via-[#131a2e] to-[#1c2450] lg:flex">
        <div className="absolute -left-32 -top-32 h-96 w-96 rounded-full bg-primary/20 blur-3xl" />
        <div className="absolute -bottom-40 -right-24 h-96 w-96 rounded-full bg-[#6d5ae0]/25 blur-3xl" />
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
          className="relative max-w-md px-10">
          <div className="mb-8 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-[#6d5ae0] shadow-lg">
              <Bot className="h-6 w-6 text-white" />
            </div>
            <div>
              <p className="text-lg font-semibold text-white">KnowledgeIQ</p>
              <p className="text-xs uppercase tracking-widest text-white/50">Enterprise AI Platform</p>
            </div>
          </div>
          <h2 className="text-3xl font-semibold leading-tight text-white">
            Turn enterprise documents into{' '}
            <span className="bg-gradient-to-r from-[#7db4f0] to-[#a99df5] bg-clip-text text-transparent">
              cited answers
            </span>
          </h2>
          <div className="mt-10 space-y-5">
            {FEATURES.map(({ icon: Icon, text }, i) => (
              <motion.div key={i} initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.2 + i * 0.12 }} className="flex items-start gap-3">
                <div className="rounded-lg bg-white/10 p-2"><Icon className="h-4 w-4 text-white" /></div>
                <p className="text-sm text-white/75">{text}</p>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Form panel */}
      <div className="flex flex-1 items-center justify-center bg-background px-6">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}
          className="w-full max-w-sm">
          <h1 className="text-2xl font-semibold text-ink">
            {mode === 'login' ? 'Welcome back' : 'Create your account'}
          </h1>
          <p className="mt-1.5 text-sm text-muted">
            {mode === 'login'
              ? 'Sign in to your knowledge workspace.'
              : 'The first account on a fresh workspace becomes the admin.'}
          </p>

          <form className="mt-8 space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
            {mode === 'register' && (
              <div>
                <Label htmlFor="fullName">Full name</Label>
                <Input id="fullName" placeholder="Ada Lovelace" autoComplete="name" {...register('fullName')} />
                <FieldError>{errors.fullName?.message}</FieldError>
              </div>
            )}
            <div>
              <Label htmlFor="email">Work email</Label>
              <Input id="email" type="email" placeholder="you@company.com" autoComplete="email" {...register('email')} />
              <FieldError>{errors.email?.message}</FieldError>
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" placeholder="••••••••"
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                {...register('password')} />
              <FieldError>{errors.password?.message}</FieldError>
            </div>

            {mode === 'login' && (
              <label className="flex cursor-pointer items-center gap-2 text-xs text-ink-2">
                <input type="checkbox" checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="accent-[var(--primary)]" />
                Keep me signed in for 30 days
              </label>
            )}

            {serverError && <p className="text-xs text-danger">{serverError}</p>}

            <Button type="submit" size="lg" className="w-full" loading={isSubmitting}>
              {mode === 'login' ? 'Sign in' : 'Create account'}
            </Button>
          </form>

          <p className="mt-6 text-center text-xs text-muted">
            {mode === 'login' ? (
              <>New workspace?{' '}
                <button className="font-medium text-primary hover:underline" onClick={() => switchMode('register')}>
                  Create an account
                </button>
              </>
            ) : (
              <>Already registered?{' '}
                <button className="font-medium text-primary hover:underline" onClick={() => switchMode('login')}>
                  Sign in instead
                </button>
              </>
            )}
          </p>
        </motion.div>
      </div>
    </div>
  )
}
