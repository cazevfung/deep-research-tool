# User Guidance Page UI Redesign

**Date:** 2025-11-14  
**Status:** Design Proposal  
**Priority:** Medium

## Overview

Redesign the User Guidance Page (`UserGuidancePage.tsx`) to have a more prominent, question-focused design with a circular action button containing a Lucide arrow icon.

---

## Current Design

The current design uses a standard form layout:
- Card container with title and subtitle
- Label with required asterisk
- Large textarea input
- Helper text below
- Rectangular button at bottom right

**Issues:**
- Question is not prominent enough
- Button design is standard (rectangular)
- Layout doesn't emphasize the conversational/question nature

---

## Proposed Design

### Design Philosophy

**"Question → Answer → Action"**

The new design emphasizes:
1. **Big, Clear Question** - The research guidance question should be the hero element
2. **Conversational Input** - User input area styled like a dialog/chat bubble
3. **Circular Action Button** - Modern, floating circular button with arrow icon

---

## Visual Layout

```
┌─────────────────────────────────────────────────────────────┐
│                                                               │
│                    [Large Spacing]                           │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                                                     │    │
│  │        在本次研究开始之前，你想强调哪些               │    │
│  │        问题重点或背景？你希望有料到给你               │    │
│  │        提供什么样的洞察？                            │    │
│  │                                                     │    │
│  │              [Large, Bold, Centered Text]           │    │
│  │              [Font Size: 24-28px]                   │    │
│  │              [Color: Dark Gray/Black]                │    │
│  │                                                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│                    [Medium Spacing]                          │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                                                     │    │
│  │  ┌─────────────────────────────────────────────┐  │    │
│  │  │                                             │  │    │
│  │  │  例如：                                      │  │    │
│  │  │  • 重点关注技术实现细节                      │  │    │
│  │  │  • 分析用户反馈和评论                        │  │    │
│  │  │  • 对比不同方案的优缺点                      │  │    │
│  │  │                                             │  │    │
│  │  │  [Placeholder text in textarea]             │  │    │
│  │  │                                             │  │    │
│  │  └─────────────────────────────────────────────┘  │    │
│  │                                                     │    │
│  │  [Textarea styled as dialog bubble]                │    │
│  │  [Rounded corners, subtle shadow]                  │    │
│  │  [Padding: 20px]                                    │    │
│  │  [Min Height: 200px]                               │    │
│  │                                                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│                    [Large Spacing]                          │
│                                                               │
│                          ┌─────┐                            │
│                          │  →  │                            │
│                          └─────┘                            │
│                    [Circular Button]                        │
│                    [Fixed at bottom center]                  │
│                    [Size: 64px diameter]                    │
│                    [ArrowRight icon from Lucide]             │
│                    [Primary color background]                │
│                    [White icon]                              │
│                    [Shadow: elevated]                        │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Structure

### Layout Hierarchy

```
<PageContainer> (max-w-4xl mx-auto px-4)
  <QuestionSection>
    <LargeQuestionText>
      "在本次研究开始之前，你想强调哪些问题重点或背景？
       你希望有料到给你提供什么样的洞察？"
  </QuestionSection>
  
  <Spacing /> (h-16)
  
  <InputSection>
    <DialogBubbleContainer>
      <Textarea
        placeholder="例如：\n• 重点关注技术实现细节\n• 分析用户反馈和评论\n• 对比不同方案的优缺点"
        styled as dialog bubble
      />
    </DialogBubbleContainer>
  </InputSection>
  
  <Spacing /> (h-16)
  
  <ActionSection>
    <CircularButton>
      <ArrowRight icon />
    </CircularButton>
  </ActionSection>
</PageContainer>
```

---

## Design Specifications

### 1. Question Section

**Typography:**
- Font Size: `text-3xl` or `text-4xl` (24-32px)
- Font Weight: `font-semibold` or `font-bold`
- Text Align: `text-center`
- Color: `text-gray-900` or `text-neutral-900`
- Line Height: `leading-relaxed` (1.6-1.8)
- Max Width: `max-w-3xl` (centered)

**Spacing:**
- Top padding: `pt-16` or `pt-20` (64-80px)
- Bottom margin: `mb-16` (64px)

**Example:**
```tsx
<div className="pt-20 pb-16">
  <h1 className="text-3xl font-semibold text-center text-gray-900 leading-relaxed max-w-3xl mx-auto">
    在本次研究开始之前，你想强调哪些问题重点或背景？
    <br />
    你希望有料到给你提供什么样的洞察？
  </h1>
</div>
```

---

### 2. Input Section (Dialog Bubble Style)

**Container:**
- Background: `bg-white`
- Border Radius: `rounded-2xl` or `rounded-3xl` (16-24px)
- Shadow: `shadow-lg` or `shadow-xl`
- Padding: `p-6` (24px)
- Max Width: `max-w-2xl` (centered)
- Border: Optional subtle border `border border-gray-200`

**Textarea:**
- Width: `w-full`
- Min Height: `min-h-[200px]` or `min-h-[240px]`
- Padding: `p-4` or `p-5` (16-20px)
- Border: `border-0` (no border, inherits from container)
- Background: `bg-transparent` or `bg-gray-50`
- Font Size: `text-base` or `text-lg`
- Line Height: `leading-relaxed`
- Focus: Remove default outline, add subtle glow
- Placeholder: `text-gray-400` or `text-gray-500`

**Example:**
```tsx
<div className="max-w-2xl mx-auto">
  <div className="bg-white rounded-2xl shadow-lg p-6 border border-gray-100">
    <Textarea
      value={userGuidance}
      onChange={(e) => setUserGuidance(e.target.value)}
      placeholder="例如：\n• 重点关注技术实现细节\n• 分析用户反馈和评论\n• 对比不同方案的优缺点"
      className="w-full min-h-[240px] p-4 border-0 bg-transparent text-base leading-relaxed placeholder:text-gray-400 focus:outline-none focus:ring-0 resize-none"
      rows={8}
      disabled={isLoading}
    />
  </div>
</div>
```

---

### 3. Circular Action Button

**Button Specifications:**
- Shape: Perfect circle
- Size: `w-16 h-16` (64px diameter)
- Position: Centered horizontally, fixed at bottom or floating
- Background: Primary color (`bg-primary-500` or `bg-yellow-400`)
- Icon: `ArrowRight` from Lucide React (or `ChevronRight`)
- Icon Size: `24px` or `28px`
- Icon Color: `text-white`
- Shadow: `shadow-lg` or `shadow-xl` (elevated appearance)
- Hover: Scale up slightly `hover:scale-110`
- Transition: Smooth `transition-all duration-200`
- Disabled State: `opacity-50 cursor-not-allowed`

**Positioning Options:**

**Option A: Fixed at Bottom Center**
```tsx
<div className="fixed bottom-8 left-1/2 transform -translate-x-1/2">
  <button className="w-16 h-16 rounded-full bg-primary-500 text-white shadow-xl hover:scale-110 transition-all duration-200 flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed">
    <ArrowRight size={24} />
  </button>
</div>
```

**Option B: Relative Positioning (in flow)**
```tsx
<div className="flex justify-center pt-16 pb-8">
  <button className="w-16 h-16 rounded-full bg-primary-500 text-white shadow-xl hover:scale-110 transition-all duration-200 flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed">
    <ArrowRight size={24} />
  </button>
</div>
```

**Option C: Floating (sticky)**
```tsx
<div className="sticky bottom-8 flex justify-center pt-16">
  <button className="w-16 h-16 rounded-full bg-primary-500 text-white shadow-xl hover:scale-110 transition-all duration-200 flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed">
    <ArrowRight size={24} />
  </button>
</div>
```

---

## Complete Component Structure

```tsx
import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight } from 'lucide-react' // or from react-feather
import { useWorkflowStore } from '../stores/workflowStore'
import { useUiStore } from '../stores/uiStore'
import { apiService } from '../services/api'
import Textarea from '../components/common/Textarea'

const UserGuidancePage: React.FC = () => {
  const navigate = useNavigate()
  const [userGuidance, setUserGuidance] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { setSessionId } = useWorkflowStore()
  const { addNotification } = useUiStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    
    const trimmedGuidance = userGuidance.trim()
    if (!trimmedGuidance) {
      setError('请输入研究指导，此字段为必填项')
      return
    }
    
    setIsLoading(true)
    // ... rest of submit logic
  }

  return (
    <div className="max-w-4xl mx-auto px-4 min-h-screen flex flex-col">
      {/* Question Section */}
      <div className="pt-20 pb-16 flex-1">
        <h1 className="text-3xl font-semibold text-center text-gray-900 leading-relaxed max-w-3xl mx-auto">
          在本次研究开始之前，你想强调哪些问题重点或背景？
          <br />
          你希望有料到给你提供什么样的洞察？
        </h1>
      </div>

      {/* Input Section - Dialog Bubble */}
      <div className="max-w-2xl mx-auto mb-16">
        <div className="bg-white rounded-2xl shadow-lg p-6 border border-gray-100">
          {error && (
            <div className="mb-4 text-sm text-red-600">
              {error}
            </div>
          )}
          <Textarea
            value={userGuidance}
            onChange={(e) => setUserGuidance(e.target.value)}
            placeholder="例如：&#10;• 重点关注技术实现细节&#10;• 分析用户反馈和评论&#10;• 对比不同方案的优缺点"
            className="w-full min-h-[240px] p-4 border-0 bg-transparent text-base leading-relaxed placeholder:text-gray-400 focus:outline-none focus:ring-0 resize-none"
            rows={8}
            disabled={isLoading}
          />
        </div>
      </div>

      {/* Action Button - Circular */}
      <div className="flex justify-center pb-8">
        <button
          type="submit"
          onClick={handleSubmit}
          disabled={isLoading || !userGuidance.trim()}
          className="w-16 h-16 rounded-full bg-primary-500 text-white shadow-xl hover:scale-110 transition-all duration-200 flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
          style={{ backgroundColor: '#FEC74A' }} // Match primary color
        >
          <ArrowRight size={24} strokeWidth={2.5} />
        </button>
      </div>
    </div>
  )
}

export default UserGuidancePage
```

---

## Design Variations

### Variation 1: Minimalist (Recommended)

- Question: Large, centered, no container
- Input: Simple rounded bubble, subtle shadow
- Button: Floating circular button at bottom center
- Spacing: Generous whitespace throughout

### Variation 2: Card-Based

- Question: Inside a subtle card container
- Input: Card with stronger shadow
- Button: Inside card or floating
- More structured appearance

### Variation 3: Conversational

- Question: Styled like a chat message (left-aligned, bubble)
- Input: Response bubble (right-aligned or centered)
- Button: Floating at bottom
- Mimics chat interface

---

## Responsive Design

### Mobile (< 768px)
- Question: `text-2xl` (smaller font)
- Input: Full width, less padding
- Button: `w-14 h-14` (slightly smaller)
- Spacing: Reduced padding/margins

### Tablet (768px - 1024px)
- Question: `text-3xl`
- Input: `max-w-xl`
- Button: `w-16 h-16`
- Standard spacing

### Desktop (> 1024px)
- Question: `text-4xl` (larger)
- Input: `max-w-2xl`
- Button: `w-16 h-16`
- Generous spacing

---

## Accessibility Considerations

1. **Button Label:**
   - Add `aria-label="继续到链接输入"` to circular button
   - Screen readers need descriptive text

2. **Error Handling:**
   - Display errors prominently above input
   - Use `aria-invalid` and `aria-describedby` on textarea

3. **Focus States:**
   - Clear focus indicators on textarea
   - Button focus ring visible

4. **Keyboard Navigation:**
   - Tab order: Textarea → Button
   - Enter key submits form

---

## Animation & Interactions

### Button Hover
- Scale: `scale-110` (10% larger)
- Shadow: Increase shadow intensity
- Transition: `duration-200 ease-in-out`

### Button Click
- Scale: `scale-95` (slight press effect)
- Duration: `duration-100`

### Loading State
- Show spinner inside button
- Disable button
- Optional: Show loading text below button

### Success State
- Brief checkmark animation
- Then navigate to next page

---

## Color Palette

**Primary Button:**
- Background: `#FEC74A` (Yellow-Orange, matches app theme)
- Hover: Slightly darker shade
- Icon: `#FFFFFF` (White)

**Text:**
- Question: `#111827` (Gray-900)
- Input Text: `#374151` (Gray-700)
- Placeholder: `#9CA3AF` (Gray-400)

**Container:**
- Background: `#FFFFFF` (White)
- Border: `#E5E7EB` (Gray-200)
- Shadow: `rgba(0, 0, 0, 0.1)`

---

## Implementation Notes

### Required Changes

1. **Remove Card Component:**
   - Current design uses `<Card>` wrapper
   - New design is more minimal, no card needed

2. **Update Textarea Component:**
   - May need to allow custom styling
   - Remove default borders/shadows
   - Support transparent background

3. **Add Lucide Icons:**
   - Install `lucide-react` if not already
   - Or use `ArrowRight` from `react-feather` (already available)

4. **Layout Structure:**
   - Use flexbox for vertical centering
   - Consider `min-h-screen` for full height
   - Center content horizontally

### Dependencies

- `lucide-react` or `react-feather` (for ArrowRight icon)
- Existing `Textarea` component (may need customization)
- Tailwind CSS classes

---

## Comparison: Before vs After

### Before (Current)
- Standard form layout
- Question in subtitle (smaller)
- Rectangular button
- Card container
- Traditional form appearance

### After (Proposed)
- Question-focused layout
- Large, prominent question
- Dialog bubble input
- Circular action button
- Modern, conversational feel

---

## Next Steps

1. **Review Design** - Confirm approach and visual style
2. **Create Mockup** - Visual mockup if needed
3. **Implement** - Update `UserGuidancePage.tsx`
4. **Test** - Responsive design and accessibility
5. **Refine** - Based on user feedback

---

## Questions to Consider

1. **Button Position:** Fixed at bottom or in-flow?
2. **Question Size:** How large should it be?
3. **Input Style:** How rounded should the bubble be?
4. **Spacing:** How much whitespace is ideal?
5. **Animation:** How much animation/interaction?

---

**Document Status:** Design Proposal - Ready for Review  
**Last Updated:** 2025-11-14

