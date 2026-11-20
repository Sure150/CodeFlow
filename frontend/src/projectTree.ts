interface ProjectFile {
  name: string
  path: string
}

export interface ProjectDirectory {
  name: string
  path: string
  directories: ProjectDirectory[]
  files: ProjectFile[]
}

export function buildProjectTree(files: readonly string[]): ProjectDirectory {
  const root: ProjectDirectory = { name: '', path: '', directories: [], files: [] }
  const directories = new Map<string, ProjectDirectory>()

  for (const file of [...files].sort((a, b) => a.localeCompare(b))) {
    const parts = file.split('/')
    const name = parts.pop()!
    let parent = root

    for (const part of parts) {
      const path = parent.path ? `${parent.path}/${part}` : part
      let directory = directories.get(path)
      if (!directory) {
        directory = { name: part, path, directories: [], files: [] }
        directories.set(path, directory)
        parent.directories.push(directory)
      }
      parent = directory
    }

    parent.files.push({ name, path: file })
  }

  return root
}
