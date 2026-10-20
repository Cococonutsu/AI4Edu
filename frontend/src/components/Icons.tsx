import type { ReactNode, SVGProps } from 'react';

interface IconProps extends SVGProps<SVGSVGElement> {
  size?: number;
}

function Icon({ size = 18, children, ...props }: IconProps & { children: ReactNode }): JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  );
}

export function PlusIcon(props: IconProps): JSX.Element {
  return (
    <Icon {...props}>
      <path d="M12 5v14M5 12h14" />
    </Icon>
  );
}

export function MenuIcon(props: IconProps): JSX.Element {
  return (
    <Icon {...props}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Icon>
  );
}

export function PencilIcon(props: IconProps): JSX.Element {
  return (
    <Icon {...props}>
      <path d="M4 20h4l10.5-10.5a2.12 2.12 0 0 0-3-3L5 17v3Z" />
      <path d="m13.5 5.5 3 3" />
    </Icon>
  );
}

export function TrashIcon(props: IconProps): JSX.Element {
  return (
    <Icon {...props}>
      <path d="M4 7h16" />
      <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
      <path d="M6.5 7 7 19a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l.5-12" />
      <path d="M10 11v6M14 11v6" />
    </Icon>
  );
}

export function SendIcon(props: IconProps): JSX.Element {
  return (
    <Icon {...props}>
      <path d="m21 3-9.5 9.5" />
      <path d="M21 3 14 21l-2.5-8.5L3 10l18-7Z" />
    </Icon>
  );
}

export function StopIcon(props: IconProps): JSX.Element {
  return (
    <Icon {...props}>
      <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none" />
    </Icon>
  );
}

export function ImageIcon(props: IconProps): JSX.Element {
  return (
    <Icon {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <circle cx="8.5" cy="9.5" r="1.5" />
      <path d="m4 17 5-5 4 4 2.5-2.5L20 18" />
    </Icon>
  );
}

export function LogOutIcon(props: IconProps): JSX.Element {
  return (
    <Icon {...props}>
      <path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4" />
      <path d="M10 8 6 12l4 4" />
      <path d="M6 12h11" />
    </Icon>
  );
}

export function CheckIcon(props: IconProps): JSX.Element {
  return (
    <Icon {...props}>
      <path d="m5 12.5 4.5 4.5L19 7" />
    </Icon>
  );
}

export function AlertIcon(props: IconProps): JSX.Element {
  return (
    <Icon {...props}>
      <path d="M12 4 3 20h18L12 4Z" />
      <path d="M12 10v4.5" />
      <circle cx="12" cy="17.3" r=".6" fill="currentColor" stroke="none" />
    </Icon>
  );
}

export function CloseIcon(props: IconProps): JSX.Element {
  return (
    <Icon {...props}>
      <path d="M6 6l12 12M18 6 6 18" />
    </Icon>
  );
}

/** 图示面板的开合。 */
export function ShapeIcon(props: IconProps): JSX.Element {
  return (
    <Icon {...props}>
      <path d="M4 20V5l8 15L20 5v15" />
    </Icon>
  );
}

export function PlayIcon(props: IconProps): JSX.Element {
  return (
    <Icon {...props}>
      <path d="M8 5.5 18 12 8 18.5Z" />
    </Icon>
  );
}

export function ChevronRightIcon(props: IconProps): JSX.Element {
  return (
    <Icon {...props}>
      <path d="m9 6 6 6-6 6" />
    </Icon>
  );
}

/** 侧栏开合：一个带竖线的方框。 */
export function SidebarIcon(props: IconProps): JSX.Element {
  return (
    <Icon {...props}>
      <rect x="3.5" y="5" width="17" height="14" rx="1.5" />
      <path d="M9.5 5v14" />
    </Icon>
  );
}
